"""Tests for the Admin Command Center modules: task_ledger, system_monitor,
docker_manager, worker_manager, and their REST API routes."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _override_admin(app):
    from app.api.auth_deps import require_admin
    app.dependency_overrides[require_admin] = lambda: {"username": "test"}


# ===========================================================================
# Task Ledger Service Tests
# ===========================================================================

class TestTaskLedgerService:
    """Direct service-level tests for app.admin.services.task_ledger."""

    def _reset_db(self, tmp_path):
        """Point DB_PATH to a temp file and wipe the tasks table."""
        from app.admin.services import task_ledger
        # Override the module-level DB_PATH
        original = task_ledger.DB_PATH
        task_ledger.DB_PATH = tmp_path / "admin_tasks.db"
        # Ensure clean slate
        if task_ledger.DB_PATH.exists():
            task_ledger.DB_PATH.unlink()
        return original

    def _restore_db(self, original):
        from app.admin.services import task_ledger
        task_ledger.DB_PATH = original

    def test_create_task(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, Priority, Status
            from app.admin.services.task_ledger import create_task

            task_in = TaskCreate(
                title="Test task",
                description="A test task",
                owner="pilot",
                priority=Priority.P1,
                status=Status.BACKLOG,
            )
            task = create_task(task_in)
            assert task.id is not None
            assert task.title == "Test task"
            assert task.owner == "pilot"
            assert task.priority == Priority.P1
            assert task.status == Status.BACKLOG
        finally:
            self._restore_db(original)

    def test_get_task(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate
            from app.admin.services.task_ledger import create_task, get_task

            task = create_task(TaskCreate(title="Fetch me"))
            fetched = get_task(task.id)
            assert fetched is not None
            assert fetched.id == task.id
            assert fetched.title == "Fetch me"
        finally:
            self._restore_db(original)

    def test_get_task_not_found(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.services.task_ledger import get_task
            assert get_task(99999) is None
        finally:
            self._restore_db(original)

    def test_list_tasks(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, Status
            from app.admin.services.task_ledger import create_task, list_tasks

            create_task(TaskCreate(title="T1", status=Status.BACKLOG))
            create_task(TaskCreate(title="T2", status=Status.IN_PROGRESS))
            create_task(TaskCreate(title="T3", status=Status.DONE))

            all_tasks = list_tasks()
            assert len(all_tasks) == 3

            backlog = list_tasks(status_filter="backlog")
            assert len(backlog) == 1
            assert backlog[0].title == "T1"
        finally:
            self._restore_db(original)

    def test_update_task(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, TaskUpdate, Status
            from app.admin.services.task_ledger import create_task, update_task

            task = create_task(TaskCreate(title="Update me"))
            updated = update_task(task.id, TaskUpdate(title="Updated", status=Status.IN_PROGRESS))
            assert updated is not None
            assert updated.title == "Updated"
            assert updated.status == Status.IN_PROGRESS
        finally:
            self._restore_db(original)

    def test_update_task_not_found(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskUpdate
            from app.admin.services.task_ledger import update_task
            assert update_task(99999, TaskUpdate(title="x")) is None
        finally:
            self._restore_db(original)

    def test_delete_task(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate
            from app.admin.services.task_ledger import create_task, delete_task, get_task

            task = create_task(TaskCreate(title="Delete me"))
            assert delete_task(task.id) is True
            assert get_task(task.id) is None
        finally:
            self._restore_db(original)

    def test_delete_task_not_found(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.services.task_ledger import delete_task
            assert delete_task(99999) is False
        finally:
            self._restore_db(original)

    def test_get_kanban(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, Status
            from app.admin.services.task_ledger import create_task, get_kanban

            create_task(TaskCreate(title="B1", status=Status.BACKLOG))
            create_task(TaskCreate(title="B2", status=Status.BACKLOG))
            create_task(TaskCreate(title="IP1", status=Status.IN_PROGRESS))
            create_task(TaskCreate(title="R1", status=Status.REVIEW))
            create_task(TaskCreate(title="D1", status=Status.DONE))

            board = get_kanban()
            assert len(board.backlog) == 2
            assert len(board.in_progress) == 1
            assert len(board.review) == 1
            assert len(board.done) == 1
        finally:
            self._restore_db(original)

    def test_get_worker_statuses(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, Status
            from app.admin.services.task_ledger import create_task, get_worker_statuses

            create_task(TaskCreate(title="W1", owner="pilot", status=Status.IN_PROGRESS))
            create_task(TaskCreate(title="W2", owner="pilot", status=Status.IN_PROGRESS))
            create_task(TaskCreate(title="W3", owner="hunter", status=Status.BACKLOG))

            statuses = get_worker_statuses()
            assert len(statuses) == 13  # 13 known workers
            pilot = next(s for s in statuses if s.name == "pilot")
            assert pilot.active_tasks == 2
            assert pilot.is_idle is False
            hunter = next(s for s in statuses if s.name == "hunter")
            assert hunter.active_tasks == 0
            assert hunter.is_idle is True
        finally:
            self._restore_db(original)

    def test_get_idle_workers(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate, Status
            from app.admin.services.task_ledger import create_task, get_idle_workers

            create_task(TaskCreate(title="Active", owner="pilot", status=Status.IN_PROGRESS))
            idle = get_idle_workers()
            assert "pilot" not in idle
            assert "hunter" in idle
        finally:
            self._restore_db(original)

    def test_detect_duplicates(self, tmp_path):
        original = self._reset_db(tmp_path)
        try:
            from app.admin.models import TaskCreate
            from app.admin.services.task_ledger import create_task, detect_duplicates

            create_task(TaskCreate(title="Fix login page bug"))
            matches = detect_duplicates("Fix login page")
            assert len(matches) >= 1
            assert matches[0]["similarity"] >= 0.75
        finally:
            self._restore_db(original)


# ===========================================================================
# System Monitor Service Tests
# ===========================================================================

class TestSystemMonitorService:
    """Tests for app.admin.services.system_monitor."""

    def test_get_health_returns_dict_with_expected_keys(self):
        from app.admin.services.system_monitor import get_health
        health = get_health()
        assert isinstance(health, dict)
        assert "cpu_percent" in health
        assert "ram_total_gb" in health
        assert "ram_used_gb" in health
        assert "ram_percent" in health
        assert "disk_total_gb" in health
        assert "disk_used_gb" in health
        assert "disk_percent" in health
        assert "processes" in health
        assert "ports" in health
        assert isinstance(health["processes"], list)
        assert isinstance(health["ports"], list)

    def test_get_ports_returns_list_of_dicts(self):
        from app.admin.services.system_monitor import get_ports
        ports = get_ports()
        assert isinstance(ports, list)
        for p in ports:
            assert "port" in p
            assert "status" in p
            assert p["status"] in ("open", "closed", "unknown")

    def test_get_ports_custom_tuple(self):
        from app.admin.services.system_monitor import get_ports
        ports = get_ports((8000, 9999))
        assert len(ports) == 2
        assert ports[0]["port"] == 8000
        assert ports[1]["port"] == 9999

    def test_get_top_processes(self):
        from app.admin.services.system_monitor import get_top_processes
        procs = get_top_processes(limit=5)
        assert isinstance(procs, list)
        assert len(procs) <= 5
        for p in procs:
            assert "name" in p
            assert "pid" in p
            assert "ram_mb" in p


# ===========================================================================
# Docker Manager Service Tests
# ===========================================================================

class TestDockerManagerService:
    """Tests for app.admin.services.docker_manager."""

    def test_list_containers_returns_dict(self):
        from app.admin.services.docker_manager import list_containers
        result = list_containers()
        assert isinstance(result, dict)
        # Either ok=True with containers, or ok=False with error
        assert "ok" in result

    def test_list_containers_structure_when_no_docker(self, monkeypatch):
        """When docker binary is missing, _docker_bin raises FileNotFoundError."""
        import shutil
        from app.admin.services import docker_manager

        original_which = shutil.which

        def fake_which(cmd):
            if cmd == "docker":
                return None
            return original_which(cmd)

        monkeypatch.setattr(shutil, "which", fake_which)
        with pytest.raises(FileNotFoundError, match="docker binary not found"):
            docker_manager.list_containers()


# ===========================================================================
# Worker Manager Service Tests
# ===========================================================================

class TestWorkerManagerService:
    """Tests for app.admin.services.worker_manager."""

    def test_get_workers_returns_list(self):
        from app.admin.services.worker_manager import get_workers
        workers = get_workers()
        assert isinstance(workers, list)
        for w in workers:
            assert "name" in w
            assert "status" in w
            assert w["status"] in ("active", "idle")
            assert "ram_mb" in w
            assert "category" in w

    def test_get_idle_workers_returns_list(self):
        from app.admin.services.worker_manager import get_idle_workers
        idle = get_idle_workers()
        assert isinstance(idle, list)
        for w in idle:
            assert w["status"] == "idle"

    def test_get_worker_count(self):
        from app.admin.services.worker_manager import get_worker_count
        counts = get_worker_count()
        assert "total" in counts
        assert "active" in counts
        assert "idle" in counts
        assert counts["total"] == counts["active"] + counts["idle"]

    def test_list_profiles_returns_list(self):
        from app.admin.services.worker_manager import list_profiles
        profiles = list_profiles()
        assert isinstance(profiles, list)


# ===========================================================================
# Admin REST API Route Tests
# ===========================================================================

class TestAdminTaskRoutes:
    """Tests for /admin/api/tasks/* REST endpoints."""

    def test_list_tasks_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        client.app.dependency_overrides.clear()

    def test_kanban_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/tasks/kanban")
        assert resp.status_code == 200
        body = resp.json()
        assert "backlog" in body
        assert "in_progress" in body
        assert "review" in body
        assert "done" in body
        client.app.dependency_overrides.clear()

    def test_create_task_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post(
            "/admin/api/tasks",
            json={"title": "API task", "description": "via API", "priority": "P1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "API task"
        assert body["priority"] == "P1"
        client.app.dependency_overrides.clear()

    def test_update_task_endpoint(self, client: TestClient):
        _override_admin(client.app)
        # Create first
        resp = client.post("/admin/api/tasks", json={"title": "To update"})
        task_id = resp.json()["id"]
        # Update
        resp = client.put(
            f"/admin/api/tasks/{task_id}",
            json={"status": "in_progress", "owner": "pilot"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"
        assert resp.json()["owner"] == "pilot"
        client.app.dependency_overrides.clear()

    def test_update_task_not_found(self, client: TestClient):
        _override_admin(client.app)
        resp = client.put("/admin/api/tasks/99999", json={"title": "x"})
        assert resp.status_code == 404
        client.app.dependency_overrides.clear()

    def test_delete_task_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/tasks", json={"title": "To delete"})
        task_id = resp.json()["id"]
        resp = client.delete(f"/admin/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        client.app.dependency_overrides.clear()

    def test_delete_task_not_found(self, client: TestClient):
        _override_admin(client.app)
        resp = client.delete("/admin/api/tasks/99999")
        assert resp.status_code == 404
        client.app.dependency_overrides.clear()

    def test_auto_assign_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/tasks/auto-assign")
        assert resp.status_code == 200
        body = resp.json()
        assert "assigned" in body
        assert "count" in body
        client.app.dependency_overrides.clear()

    def test_duplicates_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/tasks/duplicates?title=Fix%20login")
        assert resp.status_code == 200
        body = resp.json()
        assert "query" in body
        assert "matches" in body
        assert "count" in body
        client.app.dependency_overrides.clear()

    def test_worker_tasks_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/tasks/worker/pilot")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        client.app.dependency_overrides.clear()


class TestAdminSystemRoutes:
    """Tests for /admin/api/system/* REST endpoints."""

    def test_system_health_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/system/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "cpu_percent" in body
        assert "ram_total_gb" in body
        assert "processes" in body
        assert "ports" in body
        client.app.dependency_overrides.clear()

    def test_system_processes_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/system/processes")
        assert resp.status_code == 200
        body = resp.json()
        assert "processes" in body
        assert isinstance(body["processes"], list)
        client.app.dependency_overrides.clear()

    def test_system_ports_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/system/ports")
        assert resp.status_code == 200
        body = resp.json()
        assert "ports" in body
        assert isinstance(body["ports"], list)
        client.app.dependency_overrides.clear()


class TestAdminDockerRoutes:
    """Tests for /admin/api/docker/* REST endpoints."""

    def test_containers_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/containers")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_networks_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/networks")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_volumes_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/volumes")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_stats_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_container_detail_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/containers/nonexistent")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_container_logs_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/docker/containers/nonexistent/logs?lines=10")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_start_container_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/docker/containers/nonexistent/start")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_stop_container_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/docker/containers/nonexistent/stop")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_restart_container_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/docker/containers/nonexistent/restart")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()


class TestAdminWorkerRoutes:
    """Tests for /admin/api/workers/* REST endpoints."""

    def test_list_workers_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/workers")
        assert resp.status_code == 200
        body = resp.json()
        assert "workers" in body
        assert isinstance(body["workers"], list)
        client.app.dependency_overrides.clear()

    def test_idle_workers_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/workers/idle")
        assert resp.status_code == 200
        body = resp.json()
        assert "workers" in body
        assert isinstance(body["workers"], list)
        client.app.dependency_overrides.clear()

    def test_get_worker_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.get("/admin/api/workers/nonexistent")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        client.app.dependency_overrides.clear()

    def test_kill_worker_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/workers/nonexistent/kill")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()

    def test_restart_worker_endpoint(self, client: TestClient):
        _override_admin(client.app)
        resp = client.post("/admin/api/workers/nonexistent/restart")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        client.app.dependency_overrides.clear()


# ===========================================================================
# Admin routes require authentication
# ===========================================================================

class TestAdminAuthRequired:
    """Verify admin endpoints reject unauthenticated requests."""

    def test_system_requires_admin(self):
        from app.main import app
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/admin/api/system/health")
        assert resp.status_code in (401, 403)

    def test_docker_requires_admin(self):
        from app.main import app
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/admin/api/docker/containers")
        assert resp.status_code in (401, 403)

    def test_workers_requires_admin(self):
        from app.main import app
        app.dependency_overrides.clear()
        with TestClient(app) as c:
            resp = c.get("/admin/api/workers")
        assert resp.status_code in (401, 403)
