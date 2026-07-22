import json
from app.scheduling_algorithms import banker_safety

def test_case(total, allocation, max_need, names=None):
    n=len(allocation)
    need=[[max_need[i][j]-allocation[i][j] for j in range(len(total))] for i in range(n)]
    res=banker_safety(n,total,allocation,need,session_names=names)
    print('total=',total)
    print('alloc=',allocation)
    print('max=',max_need)
    print('need=',need)
    print('safe=',res['safe'])
    print('blocked=',res['deadlock_info'].get('blocked_processes'))
    print('trace len=',len(res['trace']))
    print('---')

cases=[
    ([3,3,2], [[1,0,1],[1,1,0],[1,1,0]], [[2,1,1],[1,2,1],[1,1,1]], ['P0','P1','P2']),
    ([3,3,2], [[1,0,1],[1,1,0],[0,1,1]], [[2,1,1],[1,2,1],[0,2,1]], ['P0','P1','P2']),
    ([3,3,2], [[1,0,1],[1,1,0],[1,0,1]], [[2,1,1],[1,2,1],[1,1,1]], ['P0','P1','P2']),
    ([6,3,6], [[2,1,2],[2,1,1],[1,0,2]], [[3,2,3],[3,2,2],[2,2,3]], ['P0','P1','P2']),
]
for total,allocation,max_need,names in cases:
    test_case(total,allocation,max_need,names)
