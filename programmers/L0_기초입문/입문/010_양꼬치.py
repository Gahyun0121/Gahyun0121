# 양꼬치
# 프로그래머스 L0 (기초·입문)
# 문제 링크: https://school.programmers.co.kr/learn/courses/30/lessons/120830
# 알고리즘: 기초
# 작성자: 엄가현
# 작성일: 2026. 07. 23. 14:57:19

def solution(n, k):
    answer = (n * 12000) + (k * 2000) - (n // 10)*2000
    return answer