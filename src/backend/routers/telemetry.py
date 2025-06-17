from fastapi import APIRouter, Query, HTTPException, Body
from config.db import SessionLocal
from config.models import ParsedTelemetry
from typing import Optional, List
from sqlalchemy import func

router = APIRouter()

@router.get("/telemetry")
def get_telemetry(
    log_id: int,
    message_type: Optional[str] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Query telemetry messages by log_id, message_type, and optional time range.
    """
    db = SessionLocal()
    try:
        query = db.query(ParsedTelemetry).filter(ParsedTelemetry.log_id == log_id)
        if message_type:
            query = query.filter(ParsedTelemetry.message_type == message_type)
        if start_time is not None:
            query = query.filter(ParsedTelemetry.timestamp >= start_time)
        if end_time is not None:
            query = query.filter(ParsedTelemetry.timestamp <= end_time)
        results = query.order_by(ParsedTelemetry.timestamp).limit(limit).all()
        return [
            {
                "id": row.id,
                "log_id": row.log_id,
                "message_type": row.message_type,
                "timestamp": row.timestamp,
                "data": row.data
            }
            for row in results
        ]
    finally:
        db.close()

@router.get("/telemetry/aggregate")
def aggregate_telemetry(
    log_id: int,
    message_type: str,
    field: str,
    op: str = Query("max", enum=["max", "min", "avg", "sum", "count"]),
    start_time: Optional[float] = None,
    end_time: Optional[float] = None
):
    """
    Aggregate a numeric field for a given message type (max, min, avg, sum, count).
    """
    db = SessionLocal()
    try:
        query = db.query(ParsedTelemetry).filter(
            ParsedTelemetry.log_id == log_id,
            ParsedTelemetry.message_type == message_type
        )
        if start_time is not None:
            query = query.filter(ParsedTelemetry.timestamp >= start_time)
        if end_time is not None:
            query = query.filter(ParsedTelemetry.timestamp <= end_time)
        # Extract the field from JSON data
        values = [row.data.get(field) for row in query.all() if isinstance(row.data.get(field), (int, float))]
        if not values:
            raise HTTPException(status_code=404, detail=f"No numeric values found for field '{field}'")
        if op == "max":
            result = max(values)
        elif op == "min":
            result = min(values)
        elif op == "avg":
            result = sum(values) / len(values)
        elif op == "sum":
            result = sum(values)
        elif op == "count":
            result = len(values)
        else:
            raise HTTPException(status_code=400, detail="Invalid aggregation operator")
        return {
            "log_id": log_id,
            "message_type": message_type,
            "field": field,
            "op": op,
            "result": result,
            "count": len(values)
        }
    finally:
        db.close()

@router.get("/telemetry/summary")
def telemetry_summary(log_id: int):
    """
    Return available message types, field names, and count for each type for a given log.
    """
    db = SessionLocal()
    try:
        query = db.query(ParsedTelemetry).filter(ParsedTelemetry.log_id == log_id)
        results = query.all()
        summary = {}
        for row in results:
            t = row.message_type
            if t not in summary:
                summary[t] = {"count": 0, "fields": set()}
            summary[t]["count"] += 1
            summary[t]["fields"].update(row.data.keys())
        # Convert sets to lists for JSON serialization
        for t in summary:
            summary[t]["fields"] = list(summary[t]["fields"])
        return summary
    finally:
        db.close()

@router.get("/telemetry/events")
def telemetry_events(
    log_id: int,
    message_type: str,
    field: str,
    op: str = Query("==", enum=["==", "!=", ">", "<", ">=", "<="]),
    value: float = Query(...),
    first: bool = False,
    last: bool = False
):
    """
    Find messages where a field matches a condition. Optionally return only the first or last match.
    """
    db = SessionLocal()
    try:
        query = db.query(ParsedTelemetry).filter(
            ParsedTelemetry.log_id == log_id,
            ParsedTelemetry.message_type == message_type
        ).order_by(ParsedTelemetry.timestamp)
        results = []
        for row in query:
            v = row.data.get(field)
            if v is None:
                continue
            match = False
            if op == "==" and v == value:
                match = True
            elif op == "!=" and v != value:
                match = True
            elif op == ">" and v > value:
                match = True
            elif op == "<" and v < value:
                match = True
            elif op == ">=" and v >= value:
                match = True
            elif op == "<=" and v <= value:
                match = True
            if match:
                results.append({
                    "id": row.id,
                    "log_id": row.log_id,
                    "message_type": row.message_type,
                    "timestamp": row.timestamp,
                    "data": row.data
                })
        if first and results:
            return results[0]
        if last and results:
            return results[-1]
        return results
    finally:
        db.close()

@router.post("/telemetry/custom-query")
def telemetry_custom_query(
    log_id: int,
    filters: List[dict] = Body(..., example=[{"field": "alt", "op": ">", "value": 100}]),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Flexible custom query: apply multiple filter conditions (ANDed) to message data.
    Each filter is a dict: {"field": str, "op": str, "value": any}
    """
    db = SessionLocal()
    try:
        query = db.query(ParsedTelemetry).filter(ParsedTelemetry.log_id == log_id)
        results = []
        for row in query:
            match = True
            for f in filters:
                v = row.data.get(f["field"])
                if v is None:
                    match = False
                    break
                op = f["op"]
                val = f["value"]
                if op == "==" and v != val:
                    match = False
                elif op == "!=" and v == val:
                    match = False
                elif op == ">" and not (v > val):
                    match = False
                elif op == "<" and not (v < val):
                    match = False
                elif op == ">=" and not (v >= val):
                    match = False
                elif op == "<=" and not (v <= val):
                    match = False
            if match:
                results.append({
                    "id": row.id,
                    "log_id": row.log_id,
                    "message_type": row.message_type,
                    "timestamp": row.timestamp,
                    "data": row.data
                })
            if len(results) >= limit:
                break
        return results
    finally:
        db.close() 