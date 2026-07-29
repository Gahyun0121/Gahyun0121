# 피자 나눠 먹기 (1)
# 프로그래머스 L0 (기초·입문)
# 문제 링크: https://school.programmers.co.kr/learn/courses/30/lessons/120814
# 알고리즘: 기초
# 작성자: 엄가현
# 작성일: 2026. 07. 29. 19:42:54

def solution(n):
    answer = n // 7
    if n % 7 != 0:
        answer += 1
    return answer