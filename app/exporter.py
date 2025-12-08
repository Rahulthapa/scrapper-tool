import pandas as pd
from typing import List, Dict, Any
import json
from io import BytesIO


class DataExporter:
    @staticmethod
    def to_json(data: List[Dict[str, Any]]) -> str:
        """Export data to JSON string"""
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def to_csv(data: List[Dict[str, Any]]) -> bytes:
        """Export data to CSV bytes"""
        df = pd.DataFrame(data)
        return df.to_csv(index=False).encode('utf-8')

    @staticmethod
    def to_excel(data: List[Dict[str, Any]]) -> bytes:
        """Export data to Excel bytes"""
        df = pd.DataFrame(data)
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        return buffer.getvalue()
