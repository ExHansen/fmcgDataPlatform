# Airflow + virtualenv terpisah untuk kode project (pandas/dbt/dll.), supaya dependensi project
# tidak bentrok dengan constraint Airflow. Task memanggil /opt/airflow/project-venv/bin/python.
FROM apache/airflow:3.3.2-python3.11

# LightGBM (forecasting) butuh runtime OpenMP
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
USER airflow

COPY requirements.txt /tmp/project-requirements.txt
RUN python -m venv /opt/airflow/project-venv \
 && /opt/airflow/project-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/airflow/project-venv/bin/pip install --no-cache-dir -r /tmp/project-requirements.txt
