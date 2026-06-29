"""
Migration to v1.0.0 — Initial MinIO Dataset Registry deployment.
Sets up the MinIO container with S3 API and web console.
"""
def migrate(data):
    # Ensure required fields exist
    data.setdefault("minio", {})
    data["minio"].setdefault("root_user", "winebot")
    data["minio"].setdefault("root_password", "")
    data["minio"].setdefault("extra_args", [])
    data["minio"].setdefault("additional_envs", [])

    data.setdefault("network", {})
    data["network"].setdefault("api_port", 9000)
    data["network"].setdefault("console_port", 9001)
    data["network"].setdefault("certificate_id", 0)
    data["network"].setdefault("domain", "")

    data.setdefault("storage", {})
    data["storage"].setdefault("export", {
        "type": "host_path",
        "host_path": "/mnt/Storage/models/minio"
    })
    data["storage"].setdefault("additional_storage", [])

    data.setdefault("resources", {})
    data["resources"].setdefault("limits", {
        "cpu": 2,
        "memory": 2048
    })

    return data
