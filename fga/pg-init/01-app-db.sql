-- OpenFGA 전용 'fga' DB는 POSTGRES_DB 환경변수로 자동 생성됨.
-- 앱 전용 DB를 별도 생성한다.
CREATE DATABASE app OWNER fga;
\c app
CREATE EXTENSION IF NOT EXISTS vector;
