from pathlib import Path


def test_compose_healthchecks_use_health_endpoint():
    compose = Path("compose/docker-compose.yml").read_text(encoding="utf-8")
    assert "healthcheck:" in compose
    assert "http://localhost:8000/health" in compose
    assert "http://127.0.0.1:8000/health" in compose


def test_dockerfile_has_required_oci_labels():
    dockerfile = Path("docker/Dockerfile").read_text(encoding="utf-8")
    assert "org.opencontainers.image.revision" in dockerfile
    assert "org.opencontainers.image.created" in dockerfile
    assert "org.opencontainers.image.source" in dockerfile
    assert "io.winebot.build_intent" in dockerfile


def test_release_workflow_enforces_supply_chain_guards():
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow
    assert "cosign sign --yes" in workflow
    assert "cosign verify \\" in workflow


def test_base_image_workflow_signs_digest():
    workflow = Path(".github/workflows/base-image.yml").read_text(encoding="utf-8")
    assert "provenance: mode=max" in workflow
    assert "sbom: true" in workflow
    assert "cosign sign --yes" in workflow
