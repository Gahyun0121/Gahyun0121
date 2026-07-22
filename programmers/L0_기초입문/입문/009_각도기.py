# 각도기
# 프로그래머스 L0 (기초·입문)
# 문제 링크: https://school.programmers.co.kr/learn/courses/30/lessons/120829
# 알고리즘: 기초
# 작성자: 엄가현
# 작성일: 2026. 07. 22. 15:01:33

def solution(angle):
    if 0 < angle < 90:
        answer = 1
        return answer
    elif angle == 90:
        answer = 2
        return answer
    elif 90 < angle < 180:
        answer = 3
        return answer
    else:
        answer = 4
        return answer
