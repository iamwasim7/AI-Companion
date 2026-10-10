"""Opt-in, local-only screen monitoring services."""

from app.monitoring.monitor_service import MonitorService, get_monitor_service

__all__ = ["MonitorService", "get_monitor_service"]
