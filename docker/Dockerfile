FROM python:3.10.13-bookworm

RUN useradd -ms /bin/bash sync_user
WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY --chown=sync_user /src/main.py /app/

USER sync_user

COPY --chown=sync_user /src ./src

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]