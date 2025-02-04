import logging
import kopf
import kubernetes.client as k8s
import kubernetes.config as k8s_config
import yaml

# 로깅 기본 설정: DEBUG 레벨까지 출력
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Kubernetes API 클라이언트 초기화
k8s_config.load_incluster_config()
api = k8s.CoreV1Api()
apps_api = k8s.AppsV1Api()

# NVIDIA GPU를 가진 노드만 필터링
def filter_nvidia_nodes():
    nodes = api.list_node().items
    filtered_nodes = []
    
    logger.debug(f"전체 노드 수: {len(nodes)}")
    
    for node in nodes:
        labels = node.metadata.labels or {}
        node_name = node.metadata.name
        logger.debug(f"노드 {node_name}의 레이블: {labels}")
        
        # NVIDIA GPU 라벨이 있는 경우만 binpack=true 추가
        if labels.get("nvidia.com/gpu.present") == "true":
            filtered_nodes.append(node_name)
            logger.debug(f"노드 {node_name}에 NVIDIA GPU가 있습니다.")
            if "binpack" not in labels:
                labels["binpack"] = "true"
                logger.debug(f"노드 {node_name}에 'binpack=true' 레이블 추가")
                api.patch_node(node_name, {"metadata": {"labels": labels}})
        else:
            logger.debug(f"노드 {node_name}에 NVIDIA GPU 라벨이 없습니다.")
    
    logger.debug(f"필터링된 NVIDIA 노드 목록: {filtered_nodes}")
    return filtered_nodes

# BinpackScheduler CR 생성 이벤트 핸들러
@kopf.on.create('binpackschedulers')
def create_scheduler(spec, logger, **kwargs):
    node_selector = spec.get('nodeSelector', 'binpack=true')
    logger.debug(f"spec에서 받은 nodeSelector: {node_selector}")

    # 1️⃣ NVIDIA GPU 노드만 binpack=true 라벨 추가
    nvidia_nodes = filter_nvidia_nodes()
    if not nvidia_nodes:
        logger.error("🚨 NVIDIA GPU가 있는 노드가 없습니다. Binpack Scheduler가 적용되지 않습니다.")
        return

    logger.info(f"✅ Binpack 적용 대상 NVIDIA 노드: {nvidia_nodes}")

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
                            image="cr.makina.rocks/external-hub/binpack-operator:v0.1.0",
                            ports=[k8s.V1ContainerPort(container_port=8080)],
                        )
                    ]
                ),
            ),
        ),
    )
    
    apps_api.create_namespaced_deployment(namespace="default", body=deployment)
    logger.info("✅ Binpack Scheduler 배포 완료!")
