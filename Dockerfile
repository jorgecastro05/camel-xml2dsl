FROM python:3.8-slim-buster
WORKDIR /app
COPY dist/*.whl .
RUN pip3 install *.whl && rm *.whl
RUN chown -R 1001 /app
USER 1001