# collection-agent image (027): one image, every CLI mode.
# Contract: specs/027-dockerize-collection-agent/contracts/docker-packaging.md §1.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml /app/collection-agent/pyproject.toml
COPY src /app/collection-agent/src
COPY README.md /app/collection-agent/README.md

# Editable install is load-bearing (research R2): settings.py anchors every
# data-path default to the source file location (parents[2] = the component
# root), so the source must live at /app/collection-agent — where the
# compose data mount lands. A non-editable install silently breaks every
# default path.
RUN pip install -e /app/collection-agent

EXPOSE 8022

ENTRYPOINT ["python", "-m", "collection_agent"]
CMD ["scan"]
