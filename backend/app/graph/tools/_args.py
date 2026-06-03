"""게이트 도구 인자 추출 (ADR-0032).

bind_tools가 단일 문자열 입력 Tool의 인자를 '__arg1'로 넘기는 레거시 형태를 흡수한다.
named 키(prefer) → '__arg1' → 단일 값 → '' 순으로 폴백한다.
"""


def single_text_arg(args: dict, *, prefer: str) -> str:
    if prefer in args:
        return args[prefer]
    if "__arg1" in args:
        return args["__arg1"]
    if len(args) == 1:
        return next(iter(args.values()))
    return ""
