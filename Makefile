IMAGE_NAME=myrepo/binpack-operator
TAG=latest

# 빌드
build:
	docker build -t $(IMAGE_NAME):$(TAG) .

# 로컬 테스트 실행
run:
	docker run --rm $(IMAGE_NAME):$(TAG)

# 푸시 (Docker Hub 또는 프라이빗 레지스트리)
push:
	docker push $(IMAGE_NAME):$(TAG)

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
