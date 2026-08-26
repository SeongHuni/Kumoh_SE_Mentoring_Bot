import json
import pandas as pd

FILES = [
    (1, "개설강좌 26-1학기.xlsx"),
    (2, "개설강좌 26-2 학기.xlsx")   # 파일명이 실제로 공백 포함이면 그대로 둠
]

course_info = {}

for semester, file in FILES:

    df = pd.read_excel(file)

    # 두 번째 행(전부 NaN인 설명 행) 제거
    df = df[df["교과목명"].notna()]

    for _, row in df.iterrows():

        course_name = str(row["교과목명"]).strip()

        if course_name == "" or course_name == "nan":
            continue

        professor = str(row["담당교수"]).strip()

        if "캡스톤디자인" in course_name:
            professor = "미정"

        try:
            credit = int(row["학점"])
        except:
            credit = 0

        major_type = str(row["교과목\n종류"]).strip()
        required_type = str(row["이수\n구분"]).strip()

        # 이미 등록된 과목이면 건너뜀
        if course_name in course_info:
            continue

        course_info[course_name] = {
            "semester": semester,
            "professor": professor,
            "credit": credit,
            "major_type": major_type,
            "required_type": required_type
        }

with open("course_info.json", "w", encoding="utf-8") as f:
    json.dump(course_info, f, ensure_ascii=False, indent=4)

print(f"{len(course_info)}개 과목 저장 완료")
print("course_info.json 생성 완료")