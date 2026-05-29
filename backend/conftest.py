import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

# 테스트 환경에서 JWT_SECRET 미설정 시 load_config()가 기동을 거부하므로,
# 충분한 길이의 테스트용 시크릿을 주입한다 (실제 시크릿 아님).
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest-only-32bytes-min")
