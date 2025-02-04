# Base image (Python 3.9)
FROM python:3.9-slim

# 작업 디렉토리 생성
WORKDIR /app

# 필요한 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Operator 코드 복사
COPY binpack_operator.py .

# Operator 실행
CMD ["python", "binpack_operator.py"]
