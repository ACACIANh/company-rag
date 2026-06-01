import random
from locust import HttpUser, between, task

DOC_SEARCH_QUESTIONS = [
    "연차 신청은 어떻게 하나요?",
    "온보딩 절차를 알려주세요",
    "사내 보안 정책이 궁금합니다",
    "팀 구성원은 어떻게 되나요?",
    "복리후생 혜택을 알려주세요",
]

class ChatUser(HttpUser):
    wait_time = between(1, 3)
    token: str = ""

    def on_start(self) -> None:
        res = self.client.post(
            "/auth/token",
            json={"username": "alice", "password": "alice123"},
        )
        self.token = res.json().get("access_token", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(7)
    def chat_doc_search(self) -> None:
        self.client.post(
            "/chat",
            json={"question": random.choice(DOC_SEARCH_QUESTIONS)},
            headers=self._headers(),
            name="/chat [doc_search]",
        )

    @task(1)
    def admin_cost_report(self) -> None:
        # alice는 admin 권한 없음 — 이 태스크는 AdminUser에서 처리
        pass


class AdminUser(HttpUser):
    wait_time = between(5, 10)
    token: str = ""

    def on_start(self) -> None:
        res = self.client.post(
            "/auth/token",
            json={"username": "admin", "password": "admin123"},
        )
        self.token = res.json().get("access_token", "")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task
    def cost_report(self) -> None:
        self.client.get(
            "/admin/cost/report",
            headers=self._headers(),
            name="/admin/cost/report",
        )
