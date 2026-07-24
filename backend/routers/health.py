import os
import time
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
from routers.users import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

_redis_client = None
try:
    import redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    _redis_client = redis.Redis.from_url(REDIS_URL)
except Exception:
    _redis_client = None

_fallback_traffic_cache: dict = {}
BANDWIDTH_CACHE_KEY = "duro_net_traffic"
BANDWIDTH_CACHE_TTL = 60
BANDWIDTH_MIN_INTERVAL = 0.5


def get_network_bytes() -> tuple[float, int, int]:
    """Read cumulative Rx/Tx bytes from /proc/net/dev for physical and host interfaces."""
    rx_total = 0
    tx_total = 0
    base_dir = "/proc"
    for p in ["/host/proc/1", "/host/proc", "/proc"]:
        if os.path.exists(f"{p}/net/dev"):
            base_dir = p
            break

    dev_path = f"{base_dir}/net/dev"
    # Physical NIC prefixes (eth*, en*, wl*, ib*, ppp*, wlan*)
    # Exclude virtual/container interfaces (veth*, docker*, br-*, lo*, tun*, tap*, vnet*)
    physical_prefixes = ("eth", "en", "wl", "ib", "ppp", "wlan")

    try:
        with open(dev_path, "r") as f:
            lines = f.readlines()
        for line in lines[2:]:
            parts = line.split(":")
            if len(parts) < 2:
                continue
            iface = parts[0].strip()
            if any(iface.startswith(v) for v in ("veth", "docker", "br-", "lo", "dummy", "tun", "tap", "vnet")):
                continue
            if iface.startswith(physical_prefixes):
                stats = parts[1].split()
                if len(stats) >= 9:
                    rx_total += int(stats[0])
                    tx_total += int(stats[8])
    except Exception:
        pass

    return time.monotonic(), rx_total, tx_total


def get_cpu_times() -> tuple[float, float]:
    """Read CPU times from /proc/stat. Returns (total_time, idle_time)."""
    base_dir = "/proc"
    for p in ["/host/proc", "/proc"]:
        if os.path.exists(f"{p}/stat"):
            base_dir = p
            break
    try:
        with open(f"{base_dir}/stat", "r") as f:
            for line in f:
                if line.startswith("cpu "):
                    parts = line.split()
                    times = [float(x) for x in parts[1:9]]
                    total = sum(times)
                    idle = float(parts[4]) + float(parts[5])
                    return total, idle
    except Exception:
        pass
    return 0.0, 0.0


def get_ram_usage() -> float:
    """Read RAM usage from /proc/meminfo. Returns percentage (0-100)."""
    base_dir = "/proc"
    for p in ["/host/proc", "/proc"]:
        if os.path.exists(f"{p}/meminfo"):
            base_dir = p
            break
    try:
        mem_total = 0.0
        mem_avail = 0.0
        with open(f"{base_dir}/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = float(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail = float(line.split()[1])
        if mem_total > 0:
            return 100.0 * (mem_total - mem_avail) / mem_total
    except Exception:
        pass
    return 0.0


def _store_snapshot(snapshot: dict, use_redis: bool) -> None:
    try:
        if use_redis and _redis_client:
            _redis_client.setex(
                BANDWIDTH_CACHE_KEY,
                BANDWIDTH_CACHE_TTL,
                json.dumps(snapshot),
            )
        else:
            _fallback_traffic_cache[BANDWIDTH_CACHE_KEY] = snapshot
    except Exception:
        _fallback_traffic_cache[BANDWIDTH_CACHE_KEY] = snapshot


@router.get("/health")
def get_system_health(db: Session = Depends(get_db)):
    warnings = []
    try:
        workspace_path = os.getenv("DURO_WORKSPACE_PATH", "/opt/data/duro_workspace")
        if not os.path.exists(workspace_path):
            warnings.append({
                "code": "WORKSPACE_DIR_MISSING",
                "type": "WARNING",
                "message": f"D.U.R.O. workspace directory ({workspace_path}) does not exist yet."
            })
    except Exception as e:
        logger.error(f"System health check failed: {e}")

    return {"warnings": warnings}


@router.get("/system/metrics")
def get_system_metrics():
    capacity_mbps = 1000
    limit_bytes = capacity_mbps * 125000  # 1 Mbps = 125,000 bytes/sec
    current_time, current_rx, current_tx = get_network_bytes()
    cpu_total, cpu_idle = get_cpu_times()
    ram_usage = get_ram_usage()

    prev: Optional[dict] = None
    use_redis = True if _redis_client else False
    if use_redis:
        try:
            raw = _redis_client.get(BANDWIDTH_CACHE_KEY)
            if raw:
                prev = json.loads(raw)
        except Exception:
            use_redis = False
            prev = _fallback_traffic_cache.get(BANDWIDTH_CACHE_KEY)
    else:
        prev = _fallback_traffic_cache.get(BANDWIDTH_CACHE_KEY)

    if prev is None:
        snapshot = {
            "timestamp": current_time,
            "rx_bytes": current_rx,
            "tx_bytes": current_tx,
            "rx_speed": 0.0,
            "tx_speed": 0.0,
            "cpu_total": cpu_total,
            "cpu_idle": cpu_idle,
            "cpu_usage": 0.0,
        }
        _store_snapshot(snapshot, use_redis)
        return {
            "rx_speed": 0.0,
            "tx_speed": 0.0,
            "rx_percent": 0.0,
            "tx_percent": 0.0,
            "cpu_usage": 0.0,
            "ram_usage": ram_usage,
        }

    delta_time = current_time - prev["timestamp"]

    if delta_time < BANDWIDTH_MIN_INTERVAL:
        rx_speed = float(prev.get("rx_speed", 0.0))
        tx_speed = float(prev.get("tx_speed", 0.0))
        rx_percent = min(100.0, 100.0 * rx_speed / limit_bytes) if limit_bytes > 0 else 0.0
        tx_percent = min(100.0, 100.0 * tx_speed / limit_bytes) if limit_bytes > 0 else 0.0
        return {
            "rx_speed": rx_speed,
            "tx_speed": tx_speed,
            "rx_percent": rx_percent,
            "tx_percent": tx_percent,
            "cpu_usage": float(prev.get("cpu_usage", 0.0)),
            "ram_usage": ram_usage,
        }

    rx_speed = max(0.0, (current_rx - prev["rx_bytes"]) / delta_time)
    tx_speed = max(0.0, (current_tx - prev["tx_bytes"]) / delta_time)
    rx_percent = min(100.0, 100.0 * rx_speed / limit_bytes) if limit_bytes > 0 else 0.0
    tx_percent = min(100.0, 100.0 * tx_speed / limit_bytes) if limit_bytes > 0 else 0.0

    delta_cpu_total = cpu_total - prev.get("cpu_total", 0.0)
    delta_cpu_idle = cpu_idle - prev.get("cpu_idle", 0.0)
    if delta_cpu_total > 0:
        cpu_usage = max(0.0, min(100.0, 100.0 * (1.0 - (delta_cpu_idle / delta_cpu_total))))
    else:
        cpu_usage = prev.get("cpu_usage", 0.0)

    snapshot = {
        "timestamp": current_time,
        "rx_bytes": current_rx,
        "tx_bytes": current_tx,
        "rx_speed": rx_speed,
        "tx_speed": tx_speed,
        "cpu_total": cpu_total,
        "cpu_idle": cpu_idle,
        "cpu_usage": cpu_usage,
    }
    _store_snapshot(snapshot, use_redis)

    return {
        "rx_speed": rx_speed,
        "tx_speed": tx_speed,
        "rx_percent": rx_percent,
        "tx_percent": tx_percent,
        "cpu_usage": cpu_usage,
        "ram_usage": ram_usage,
    }


@router.get("/logs/system", response_model=List[schemas.SystemLogResponse])
def get_system_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    return db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(limit).all()


@router.get("/logs/audit", response_model=List[schemas.AuditLogResponse])
def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    return db.query(models.AuditLog).order_by(models.AuditLog.created_at.desc()).limit(limit).all()
