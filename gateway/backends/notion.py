"""Backend Notion — API REST en lecture seule via httpx."""

import json
import os
from typing import Any

from gateway.config import logger


class NotionBackend:
    """Backend Notion en lecture seule via l'API officielle.
    Utilise httpx pour les appels REST.
    Token résolu dans l'ordre : variable d'env NOTION_TOKEN → PostgreSQL
    (integration_tokens via reload_from_db) → mode mock.
    """

    API_BASE = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self):
        self.token = ""
        self.headers: dict[str, str] = {}
        self.mode = "mock"
        self._init_client()

    def _init_client(self):
        token = os.getenv("NOTION_TOKEN", "")
        if not token:
            logger.info("NOTION | NOTION_TOKEN non défini — en attente du chargement depuis la DB.")
            return

        self._connect(token)

    def _connect(self, token: str):
        """Configure le client Notion avec un token donné."""
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self.API_VERSION,
            "Content-Type": "application/json",
        }
        self.mode = "real"
        logger.info("NOTION | Connecté à l'API Notion (mode lecture seule)")

    async def reload_from_db(self):
        """Recharge le token depuis la DB (appelé au startup après init_db)."""
        from gateway.backends.integration_store import get_token
        token = await get_token("notion")
        if token:
            self._connect(token)
            logger.info("NOTION | Token rechargé depuis la base de données")

    async def search(self, query: str = "", filter_type: str = "") -> list[dict]:
        if self.mode == "mock":
            return self._mock_search(query)
        try:
            import httpx
            payload: dict[str, Any] = {}
            if query:
                payload["query"] = query
            if filter_type in ("page", "database"):
                payload["filter"] = {"value": filter_type, "property": "object"}
            payload["page_size"] = 20
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.API_BASE}/search", headers=self.headers,
                                         json=payload, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            return [self._format_item(item) for item in data.get("results", [])]
        except Exception as e:
            logger.error("NOTION_SEARCH | Erreur : %s", str(e))
            return [{"error": "Erreur lors de la recherche Notion. Réessayez ultérieurement."}]

    async def read_page(self, page_id: str) -> dict:
        if self.mode == "mock":
            return self._mock_page(page_id)
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                page_resp = await client.get(f"{self.API_BASE}/pages/{page_id}",
                                             headers=self.headers, timeout=15)
                page_resp.raise_for_status()
                page_data = page_resp.json()
                blocks_resp = await client.get(f"{self.API_BASE}/blocks/{page_id}/children?page_size=100",
                                               headers=self.headers, timeout=15)
                blocks_resp.raise_for_status()
                blocks_data = blocks_resp.json()

            title = self._extract_title(page_data)
            content = self._blocks_to_text(blocks_data.get("results", []))
            return {
                "id": page_id, "title": title,
                "url": page_data.get("url", ""),
                "created_time": page_data.get("created_time", ""),
                "last_edited_time": page_data.get("last_edited_time", ""),
                "content": content,
            }
        except Exception as e:
            logger.error("NOTION_READ_PAGE | Erreur : %s", str(e))
            return {"error": "Erreur lors de la lecture de la page Notion. Réessayez ultérieurement."}

    async def query_database(self, database_id: str, filter_json: str = "") -> list[dict]:
        if self.mode == "mock":
            return self._mock_database(database_id)
        try:
            import httpx
            payload: dict[str, Any] = {"page_size": 50}
            if filter_json:
                try:
                    payload["filter"] = json.loads(filter_json)
                except json.JSONDecodeError:
                    return [{"error": f"Filtre JSON invalide : {filter_json}"}]
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.API_BASE}/databases/{database_id}/query",
                                         headers=self.headers, json=payload, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            return [{
                "id": item.get("id", ""),
                "url": item.get("url", ""),
                "created_time": item.get("created_time", ""),
                "last_edited_time": item.get("last_edited_time", ""),
                "properties": self._extract_properties(item.get("properties", {})),
            } for item in data.get("results", [])]
        except Exception as e:
            logger.error("NOTION_QUERY_DB | Erreur : %s", str(e))
            return [{"error": "Erreur lors de la requête Notion. Réessayez ultérieurement."}]

    # ── Helpers ──

    def _format_item(self, item: dict) -> dict:
        obj_type = item.get("object", "")
        result: dict[str, Any] = {
            "id": item.get("id", ""), "type": obj_type,
            "url": item.get("url", ""),
            "last_edited_time": item.get("last_edited_time", ""),
        }
        if obj_type == "page":
            result["title"] = self._extract_title(item)
        elif obj_type == "database":
            title_parts = item.get("title", [])
            result["title"] = "".join(t.get("plain_text", "") for t in title_parts)
        return result

    def _extract_title(self, page: dict) -> str:
        props = page.get("properties", {})
        for prop in props.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in title_parts)
        return "(sans titre)"

    def _extract_properties(self, properties: dict) -> dict:
        result: dict[str, Any] = {}
        for name, prop in properties.items():
            prop_type = prop.get("type", "")
            if prop_type == "title":
                result[name] = "".join(t.get("plain_text", "") for t in prop.get("title", []))
            elif prop_type == "rich_text":
                result[name] = "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
            elif prop_type == "number":
                result[name] = prop.get("number")
            elif prop_type == "select":
                sel = prop.get("select")
                result[name] = sel.get("name", "") if sel else ""
            elif prop_type == "multi_select":
                result[name] = [s.get("name", "") for s in prop.get("multi_select", [])]
            elif prop_type == "status":
                st = prop.get("status")
                result[name] = st.get("name", "") if st else ""
            elif prop_type == "date":
                d = prop.get("date")
                result[name] = d.get("start", "") if d else ""
            elif prop_type == "checkbox":
                result[name] = prop.get("checkbox", False)
            elif prop_type == "url":
                result[name] = prop.get("url", "")
            elif prop_type == "email":
                result[name] = prop.get("email", "")
            elif prop_type == "phone_number":
                result[name] = prop.get("phone_number", "")
            elif prop_type == "people":
                result[name] = [p.get("name", p.get("id", "")) for p in prop.get("people", [])]
            elif prop_type == "relation":
                result[name] = [r.get("id", "") for r in prop.get("relation", [])]
            elif prop_type == "formula":
                f_val = prop.get("formula", {})
                result[name] = f_val.get(f_val.get("type", ""), "")
            elif prop_type == "rollup":
                r_val = prop.get("rollup", {})
                result[name] = r_val.get(r_val.get("type", ""), "")
            else:
                result[name] = f"[{prop_type}]"
        return result

    def _blocks_to_text(self, blocks: list[dict]) -> str:
        lines = []
        for block in blocks:
            block_type = block.get("type", "")
            content = block.get(block_type, {})
            rich_text = content.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)
            if block_type in ("paragraph", "quote", "callout"):
                if text:
                    lines.append(text)
            elif block_type.startswith("heading_"):
                level = block_type[-1]
                lines.append(f"{'#' * int(level)} {text}")
            elif block_type == "bulleted_list_item":
                lines.append(f"• {text}")
            elif block_type == "numbered_list_item":
                lines.append(f"- {text}")
            elif block_type == "to_do":
                checked = "✓" if content.get("checked", False) else "○"
                lines.append(f"{checked} {text}")
            elif block_type == "code":
                lang = content.get("language", "")
                lines.append(f"```{lang}\n{text}\n```")
            elif block_type == "divider":
                lines.append("---")
            elif block_type == "toggle":
                lines.append(f"▸ {text}")
            elif block_type == "table_row":
                cells = content.get("cells", [])
                row = " | ".join("".join(c.get("plain_text", "") for c in cell) for cell in cells)
                lines.append(row)
            elif text:
                lines.append(text)
        return "\n".join(lines)

    # ── Mock fallback ──

    def _mock_search(self, query: str) -> list[dict]:
        return [
            {"id": "page-001", "type": "page", "title": "Playbook — Réponse aux incidents",
             "url": "https://notion.so/mock-page-001", "last_edited_time": "2026-04-01T10:00:00Z"},
            {"id": "db-001", "type": "database", "title": "CMDB — Inventaire des postes",
             "url": "https://notion.so/mock-db-001", "last_edited_time": "2026-04-02T14:00:00Z"},
        ]

    def _mock_page(self, page_id: str) -> dict:
        return {
            "id": page_id, "title": "Playbook — Réponse aux incidents (MOCK)",
            "content": "# Playbook\n\n1. Identifier la menace\n2. Contenir\n3. Éradiquer\n4. Récupérer",
            "url": "https://notion.so/mock", "created_time": "2026-01-15", "last_edited_time": "2026-04-01",
        }

    def _mock_database(self, database_id: str) -> list[dict]:
        return [
            {"id": "row-1", "url": "https://notion.so/mock-row-1",
             "properties": {"Name": "PC025", "Owner": "Alice Martin", "OS": "Windows 11", "Status": "Active"}},
            {"id": "row-2", "url": "https://notion.so/mock-row-2",
             "properties": {"Name": "MAC-042", "Owner": "Bob Johnson", "OS": "macOS 15", "Status": "Active"}},
        ]
