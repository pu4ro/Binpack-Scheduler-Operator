#!/bin/bash

# 생성할 파일 목록
FILES=("Dockerfile" "requirements.txt" "Makefile" "operator.py" "binpackscheduler-crd.yaml" "binpack-operator-deployment.yaml" "binpack-operator-sa.yaml" "my-binpack.yaml")

# 기존 파일이 있으면 삭제
for file in "${FILES[@]}"; do
    if [ -f "./$file" ]; then
        echo "🛑 기존 파일 삭제: $file"
        rm "./$file"
    fi
done

# Dockerfile 생성
cat <<EOF > ./Dockerfile
# Base image (Python 3.9)
FROM python:3.9-slim

# 작업 디렉토리 생성
WORKDIR /app

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Operator 코드 복사
COPY operator.py .

# Operator 실행
CMD ["python", "operator.py"]
EOF

echo "✅ Dockerfile 생성 완료"

# requirements.txt 생성
cat <<EOF > ./requirements.txt
kopf
kubernetes
PyYAML
EOF

echo "✅ requirements.txt 생성 완료"

# Makefile 생성
cat <<EOF > ./Makefile
IMAGE_NAME=myrepo/binpack-operator
TAG=latest

# 빌드
build:
	docker build -t \$(IMAGE_NAME):\$(TAG) .

# 로컬 테스트 실행
run:
	docker run --rm \$(IMAGE_NAME):\$(TAG)

# 푸시 (Docker Hub 또는 프라이빗 레지스트리)
push:
	docker push \$(IMAGE_NAME):\$(TAG)

# Operator 배포
deploy:
	kubectl apply -f binpackscheduler-crd.yaml
	kubectl apply -f binpack-operator-deployment.yaml
	kubectl apply -f binpack-operator-sa.yaml

# Operator 삭제
clean:
	kubectl delete -f binpack-operator-deployment.yaml
	kubectl delete -f binpackscheduler-crd.yaml
	kubectl delete -f binpack-operator-sa.yaml

# 전체 빌드 및 배포
all: build push deploy
EOF

echo "✅ Makefile 생성 완료"

# operator.py 생성 (NVIDIA GPU 체크)
cat <<EOF > ./operator.py
import kopf
import kubernetes.client as k8s
import kubernetes.config as k8s_config
import yaml

# Kubernetes API 클라이언트 초기화
k8s_config.load_incluster_config()
api = k8s.CoreV1Api()
apps_api = k8s.AppsV1Api()

# NVIDIA GPU를 가진 노드만 필터링
def filter_nvidia_nodes():
    nodes = api.list_node().items
    filtered_nodes = []
    
    for node in nodes:
        labels = node.metadata.labels

        # NVIDIA GPU 라벨이 있는 경우만 binpack=true 추가
        if "nvidia.com/gpu.present" in labels and labels["nvidia.com/gpu.present"] == "true":
            filtered_nodes.append(node.metadata.name)
            if "binpack" not in labels:
                labels["binpack"] = "true"
                api.patch_node(node.metadata.name, {"metadata": {"labels": labels}})
    
    return filtered_nodes

# BinpackScheduler CR 생성 이벤트 핸들러
@kopf.on.create('binpackschedulers')
def create_scheduler(spec, **kwargs):
    node_selector = spec.get('nodeSelector', 'binpack=true')

    # 1️⃣ NVIDIA GPU 노드만 binpack=true 라벨 추가
    nvidia_nodes = filter_nvidia_nodes()
    if not nvidia_nodes:
        print("🚨 NVIDIA GPU가 있는 노드가 없습니다. Binpack Scheduler가 적용되지 않습니다.")
        return

    print(f"✅ Binpack 적용 대상 NVIDIA 노드: {nvidia_nodes}")

    # 2️⃣ Scheduler Extender 배포
    deployment = k8s.V1Deployment(
        metadata=k8s.V1ObjectMeta(name="binpack-scheduler-extender"),
        spec=k8s.V1DeploymentSpec(
            replicas=1,
            selector=k8s.V1LabelSelector(match_labels={"app": "binpack-scheduler"}),
            template=k8s.V1PodTemplateSpec(
                metadata=k8s.V1ObjectMeta(labels={"app": "binpack-scheduler"}),
                spec=k8s.V1PodSpec(
                    containers=[
                        k8s.V1Container(
                            name="scheduler-extender",
                            image="myrepo/binpack-scheduler:latest",
                            ports=[k8s.V1ContainerPort(container_port=8080)],
                        )
                    ]
                ),
            ),
        ),
    )
    apps_api.create_namespaced_deployment(namespace="default", body=deployment)

    print("✅ Binpack Scheduler 배포 완료!")

EOF

echo "✅ operator.py 생성 완료"

# CRD 생성
cat <<EOF > ./binpackscheduler-crd.yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: binpackschedulers.example.com
spec:
  group: example.com
  names:
    kind: BinpackScheduler
    listKind: BinpackSchedulerList
    plural: binpackschedulers
    singular: binpackscheduler
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                nodeSelector:
                  type: string
EOF

echo "✅ binpackscheduler-crd.yaml 생성 완료"

# Operator Deployment 생성
cat <<EOF > ./binpack-operator-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: binpack-operator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: binpack-operator
  template:
    metadata:
      labels:
        app: binpack-operator
    spec:
      serviceAccountName: binpack-operator-sa
      containers:
      - name: operator
        image: myrepo/binpack-operator:latest
        imagePullPolicy: Always
EOF

echo "✅ binpack-operator-deployment.yaml 생성 완료"

# ServiceAccount 생성
cat <<EOF > ./binpack-operator-sa.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: binpack-operator-sa
EOF

echo "✅ binpack-operator-sa.yaml 생성 완료"

# BinpackScheduler 리소스 생성
cat <<EOF > ./my-binpack.yaml
apiVersion: example.com/v1
kind: BinpackScheduler
metadata:
  name: my-binpack
spec:
  nodeSelector: "binpack=true"
EOF

echo "✅ my-binpack.yaml 생성 완료"

echo "🎉 모든 파일 생성 완료! 실행하려면 'make all'을 사용하세요!"

