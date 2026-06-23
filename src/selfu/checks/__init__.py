"""Aggregator for all check categories."""

from . import cpu, disk, health, memory, network, security, system, updates


def collect_all():
    return {
        "network": network.check_all(),
        "cpu": cpu.check_cpu(),
        "disk": disk.check_disk(),
        "inodes": disk.check_inodes(),
        "memory": memory.check_memory(),
        "system": system.check_all(),
        "health": health.check_all(),
        "security": security.check_all(),
        "updates": updates.check_updates(),
    }
