# 짝수의 합
# 프로그래머스 L0 (기초·입문)
# 문제 링크: https://school.programmers.co.kr/learn/courses/30/lessons/120831
# 알고리즘: 기초
# 작성자: 엄가현
# 작성일: 2026. 07. 27. 20:32:47

def solution(n):
    answer = 0
    for i in range(0,n+1):
        if i % 2 == 0:
            answer += i
    
    return answer