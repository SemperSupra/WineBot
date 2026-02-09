from pathlib import Path


def test_dockerfile_declares_build_intent():
    dockerfile = Path("docker/Dockerfile").read_text()
    assert "ARG BASE_IMAGE=" in dockerfile
    assert "FROM ${BASE_IMAGE} AS base-runtime" in dockerfile
    assert "FROM base-runtime AS intent-dev" in dockerfile
    assert "FROM base-runtime AS intent-test" in dockerfile
    assert "FROM base-runtime AS intent-rel" in dockerfile
    assert "FROM base-runtime AS intent-rel-runner" in dockerfile
    assert "COPY requirements-rel.txt" in dockerfile
    assert "COPY requirements-devtest.txt" in dockerfile
    assert "LABEL io.winebot.build_intent" in dockerfile
    assert "ENV WINEPREFIX=/wineprefix \\" in dockerfile
    assert "ENV BUILD_INTENT=rel" in dockerfile
    assert "ENV BUILD_INTENT=rel-runner" in dockerfile


def test_compose_wires_build_intent():
    compose = Path("compose/docker-compose.yml").read_text()
    assert "BUILD_INTENT: ${BUILD_INTENT:-rel}" in compose
    assert "target: intent-${BUILD_INTENT:-rel}" in compose
    assert "BASE_IMAGE: ${BASE_IMAGE:-" in compose
    assert "args:" in compose
    assert "image: winebot:${WINEBOT_IMAGE_VERSION:-local}-${BUILD_INTENT:-rel}" in compose
