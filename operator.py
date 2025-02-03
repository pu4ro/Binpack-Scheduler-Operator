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

