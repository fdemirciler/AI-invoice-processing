"""Cloud Tasks helper service for enqueuing processing jobs."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from google.cloud import tasks_v2

logger = logging.getLogger(__name__)


@dataclass
class TasksConfig:
    project: str
    region: str
    queue: str
    target_url: str
    service_account_email: str
    emulate: bool = True


class CloudTasksService:
    """Wrapper for creating HTTP tasks to trigger processing."""

    def __init__(self, cfg: TasksConfig) -> None:
        self.cfg = cfg
        self._client = tasks_v2.CloudTasksClient()

    def enqueue_job(self, job_id: str, session_id: str) -> Optional[str]:
        """Create a task to call the worker endpoint with OIDC.

        Returns the task name on success, or None if emulated/no-op.
        Raises on irrecoverable API errors.
        """
        if self.cfg.emulate or not all([
            self.cfg.project, self.cfg.region, self.cfg.queue,
            self.cfg.target_url, self.cfg.service_account_email,
        ]):
            logger.info("Tasks emulation/no-op: skipping enqueue for job %s", job_id)
            return None

        parent = self._client.queue_path(self.cfg.project, self.cfg.region, self.cfg.queue)
        payload = {"jobId": job_id, "sessionId": session_id}
        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": self.cfg.target_url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": self.cfg.service_account_email,
                    "audience": self.cfg.target_url,
                },
            }
        }
        response = self._client.create_task(request={"parent": parent, "task": task})
        logger.info("Created task %s for job %s", response.name, job_id)
        return response.name
