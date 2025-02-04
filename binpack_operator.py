import logging
import kopf
import kubernetes.client as k8s
import kubernetes.config as k8s_config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Kubernetes API 클라이언트 초기화
try:
    k8s_config.load_incluster_config()
except Exception as e:
    logger.exception("In-cluster config 로드 실패: %s", e)
    raise

api = k8s.CoreV1Api()
apps_api = k8s.AppsV1Api()

def filter_nvidia_nodes():
    try:
        nodes = api.list_node().items
    except Exception as e:
        logger.exception("노드 목록 가져오기 실패: %s", e)
        raise

    filtered_nodes = []
    logger.debug(f"전체 노드 수: {len(nodes)}")
    
    for node in nodes:
        labels = node.metadata.labels or {}
        node_name = node.metadata.name
        logger.debug(f"노드 {node_name}의 레이블: {labels}")
        
        if labels.get("nvidia.com/gpu.present") == "true":
            filtered_nodes.append(node_name)
            logger.debug(f"노드 {node_name}에 NVIDIA GPU가 있습니다.")
            if "binpack" not in labels:
                labels["binpack"] = "true"
                logger.debug(f"노드 {node_name}에 'binpack=true' 레이블 추가")
                try:
                    api.patch_node(node_name, {"metadata": {"labels": labels}})
                except Exception as e:
                    logger.exception("노드 %s 레이블 패치 실패: %s", node_name, e)
        else:
            logger.debug(f"노드 {node_name}에 NVIDIA GPU 라벨이 없습니다.")
    
    logger.debug(f"필터링된 NVIDIA 노드 목록: {filtered_nodes}")
    return filtered_nodes

@kopf.on.create('binpackschedulers')
def create_scheduler(spec, logger, **kwargs):
    node_selector = spec.get('nodeSelector', 'binpack=true')
    logger.debug(f"spec에서 받은 nodeSelector: {node_selector}")

    try:
        nvidia_nodes = filter_nvidia_nodes()
    except Exception as e:
        logger.exception("NVIDIA 노드 필터링 중 에러 발생: %s", e)
        raise

    if not nvidia_nodes:
        logger.error("🚨 NVIDIA GPU가 있는 노드가 없습니다. Binpack Scheduler가 적용되지 않습니다.")
        return

    logger.info(f"✅ Binpack 적용 대상 NVIDIA 노드: {nvidia_nodes}")

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
    try:
        apps_api.create_namespaced_deployment(namespace="default", body=deployment)
        logger.info("✅ Binpack Scheduler 배포 완료!")
    except Exception as e:
        logger.exception("배포 생성 실패: %s", e)
        raise
