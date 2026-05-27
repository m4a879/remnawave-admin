"""Auto-extracted from shared/violation_detector.py."""
import asyncio
import json
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as tz
from itertools import combinations
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from shared.analyzers.models import (
    ViolationAction, TemporalScore, GeoScore, ASNScore, ProfileScore,
    DeviceScore, HwidScore, UserAgentClassification, SuspiciousAgent,
    UserAgentScore, ViolationScore,
)
from shared.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from shared.logger import logger

class DeviceFingerprintAnalyzer:
    """
    Анализ устройств по fingerprint (User-Agent и другие данные).
    
    Правила:
    - Один fingerprint, разные IP = 0 (один человек, разные сети)
    - Разные версии одного клиента = +10
    - Разные клиенты = +25
    - Разные ОС = +40
    - > 3 разных fingerprint одновременно = +60
    """
    
    def _extract_fingerprint(self, connection: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Извлекает fingerprint из данных подключения.
        
        Args:
            connection: Данные подключения
        
        Returns:
            Словарь с fingerprint данными или None
        """
        device_info = connection.get("device_info")
        user_agent = connection.get("user_agent")
        
        if not device_info and not user_agent:
            return None
        
        fingerprint = {}
        
        # Парсим User-Agent если доступен
        if user_agent:
            fingerprint['user_agent'] = user_agent
            # Простой парсинг User-Agent для определения ОС и клиента
            ua_lower = user_agent.lower()
            
            # Определяем ОС
            if 'android' in ua_lower:
                fingerprint['os_family'] = 'Android'
            elif 'ios' in ua_lower or 'iphone' in ua_lower or 'ipad' in ua_lower:
                fingerprint['os_family'] = 'iOS'
            elif 'windows' in ua_lower:
                fingerprint['os_family'] = 'Windows'
            elif 'linux' in ua_lower:
                fingerprint['os_family'] = 'Linux'
            elif 'macos' in ua_lower or 'mac os' in ua_lower:
                fingerprint['os_family'] = 'macOS'
            else:
                fingerprint['os_family'] = 'Unknown'
            
            # Определяем клиент
            if 'v2rayng' in ua_lower or 'v2ray' in ua_lower:
                fingerprint['client_type'] = 'V2RayNG'
            elif 'shadowrocket' in ua_lower:
                fingerprint['client_type'] = 'Shadowrocket'
            elif 'clash' in ua_lower:
                fingerprint['client_type'] = 'Clash'
            elif 'surge' in ua_lower:
                fingerprint['client_type'] = 'Surge'
            else:
                fingerprint['client_type'] = 'Unknown'
        
        # Используем device_info если доступен
        if device_info:
            if isinstance(device_info, dict):
                fingerprint.update(device_info)
            elif isinstance(device_info, str):
                # Пытаемся распарсить JSON строку
                try:
                    device_dict = json.loads(device_info)
                    fingerprint.update(device_dict)
                except (json.JSONDecodeError, TypeError):
                    fingerprint['device_info_raw'] = device_info
        
        return fingerprint if fingerprint else None
    
    def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]],
        user_device_count: int = 1,
    ) -> DeviceScore:
        """
        Анализирует fingerprint устройств.

        Args:
            connections: Активные подключения
            connection_history: История подключений
            user_device_count: Лимит устройств пользователя

        Returns:
            DeviceScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        
        # Собираем все подключения для анализа
        all_connections = []
        for conn in connections:
            all_connections.append({
                'ip_address': str(conn.ip_address),
                'device_info': getattr(conn, 'device_info', None),
                'user_agent': getattr(conn, 'user_agent', None)
            })
        
        now = datetime.utcnow()
        for conn in connection_history:
            conn_time = conn.get('connected_at')
            if isinstance(conn_time, datetime):
                if conn_time.tzinfo:
                    conn_time = conn_time.astimezone(tz.utc).replace(tzinfo=None)
                if (now - conn_time).total_seconds() > 86400:  # > 24 часа
                    continue
            all_connections.append(conn)

        # Извлекаем fingerprint для каждого подключения
        fingerprints: List[Dict[str, str]] = []
        for conn in all_connections:
            fp = self._extract_fingerprint(conn)
            if fp:
                fingerprints.append(fp)
        
        if not fingerprints:
            return DeviceScore(
                score=0.0,
                reasons=[],
                unique_fingerprints_count=0,
                different_os_count=0
            )
        
        # Группируем по уникальным fingerprint
        unique_fingerprints: List[Dict[str, str]] = []
        seen_fps = set()
        
        for fp in fingerprints:
            # Создаём ключ для сравнения fingerprint
            fp_key = (
                fp.get('os_family', ''),
                fp.get('client_type', ''),
            )
            
            if fp_key not in seen_fps:
                seen_fps.add(fp_key)
                unique_fingerprints.append(fp)
        
        unique_fingerprints_count = len(unique_fingerprints)
        
        # Подсчитываем уникальные ОС (исключаем Unknown)
        os_families = set(fp.get('os_family', 'Unknown') for fp in unique_fingerprints)
        os_families_known = sorted([os for os in os_families if os and os != 'Unknown'])
        different_os_count = len(os_families_known) if os_families_known else len(os_families)

        # Подсчитываем уникальные клиенты (исключаем Unknown)
        client_types = set(fp.get('client_type', 'Unknown') for fp in unique_fingerprints)
        client_types_known = sorted([client for client in client_types if client and client != 'Unknown'])
        different_clients_count = len(client_types_known) if client_types_known else len(client_types)

        # Если количество fingerprints не превышает лимит устройств — это нормально
        if unique_fingerprints_count <= user_device_count:
            return DeviceScore(
                score=0.0,
                reasons=[],
                unique_fingerprints_count=unique_fingerprints_count,
                different_os_count=different_os_count,
                os_list=os_families_known if os_families_known else None,
                client_list=client_types_known if client_types_known else None
            )

        # Оценка на основе различий (с учётом лимита устройств)
        excess = unique_fingerprints_count - user_device_count
        if excess >= 3 or unique_fingerprints_count > 3:
            score = 60.0
            reasons.append(f"Много устройств ({unique_fingerprints_count}) при лимите {user_device_count}")
        elif different_os_count > user_device_count and different_os_count >= 3:
            score = 40.0
            reasons.append(f"Разные ОС ({different_os_count}) при лимите {user_device_count}: {', '.join(os_families_known or list(os_families))}")
        elif different_clients_count > user_device_count:
            score = 25.0
            reasons.append(f"Разные клиенты ({different_clients_count}) при лимите {user_device_count}: {', '.join(client_types_known or list(client_types))}")
        elif excess >= 1:
            score = 10.0
            reasons.append(f"Превышение лимита: {unique_fingerprints_count} fingerprints при лимите {user_device_count}")

        return DeviceScore(
            score=min(score, 100.0),
            reasons=reasons,
            unique_fingerprints_count=unique_fingerprints_count,
            different_os_count=different_os_count,
            os_list=os_families_known if os_families_known else None,
            client_list=client_types_known if client_types_known else None
        )


