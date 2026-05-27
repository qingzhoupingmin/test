"""用例依赖解析器 — 拓扑排序 + 循环依赖检测 + 依赖传递"""

from collections import deque
from typing import Dict, List, Optional, Set, Tuple

from loguru import logger

from core.exceptions import CaseDependencyError
from core.models import ApiCaseModel


class CaseDependencyResolver:
    """用例依赖解析器

    功能:
    1. 拓扑排序 — 确保依赖项先于依赖方执行
    2. 循环依赖检测 — 避免死循环
    3. 依赖传递 — 依赖项的提取变量自动注入到下游用例
    """

    @classmethod
    def resolve(cls, cases: List[ApiCaseModel]) -> List[ApiCaseModel]:
        """对用例列表进行拓扑排序，返回执行顺序"""
        if not cases:
            return []

        case_map: Dict[str, ApiCaseModel] = {c.case_id: c for c in cases}

        # 构建依赖图
        in_degree: Dict[str, int] = {}
        adjacency: Dict[str, List[str]] = {}

        for case in cases:
            cid = case.case_id
            if cid not in in_degree:
                in_degree[cid] = 0
            if cid not in adjacency:
                adjacency[cid] = []

            if case.depends_on:
                dep_id = case.depends_on.strip()
                if not dep_id:
                    continue
                # 依赖项不存在于当前批次
                if dep_id not in case_map:
                    logger.warning("用例 {} 依赖的 {} 不在当前批次中，跳过依赖", cid, dep_id)
                    continue
                # 依赖自身
                if dep_id == cid:
                    raise CaseDependencyError(f"用例 {cid} 不能依赖自身")
                # 入度+1，邻接边
                in_degree[cid] = in_degree.get(cid, 0) + 1
                adjacency.setdefault(dep_id, []).append(cid)

        # 循环依赖检测（拓扑排序 BFS）
        queue: deque = deque([cid for cid, deg in in_degree.items() if deg == 0])
        sorted_ids: List[str] = []

        while queue:
            current = queue.popleft()
            sorted_ids.append(current)
            for neighbor in adjacency.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_ids) != len(cases):
            # 存在循环依赖
            remaining = [cid for cid in case_map if cid not in sorted_ids]
            raise CaseDependencyError(
                f"检测到循环依赖: {', '.join(remaining)}"
            )

        sorted_cases = [case_map[cid] for cid in sorted_ids]
        logger.debug("依赖排序完成，执行顺序: {}", [c.case_id for c in sorted_cases])
        return sorted_cases

    @classmethod
    def get_dependency_chain(cls, case_id: str, case_map: Dict[str, ApiCaseModel]) -> List[str]:
        """获取某个用例的完整依赖链（递归上游）"""
        chain: List[str] = []
        visited: Set[str] = set()

        def traverse(cid: str):
            if cid in visited:
                return
            visited.add(cid)
            case = case_map.get(cid)
            if case and case.depends_on and case.depends_on in case_map:
                traverse(case.depends_on)
            chain.append(cid)

        traverse(case_id)
        return chain

    @classmethod
    def resolve_with_transfer(
        cls,
        cases: List[ApiCaseModel],
        context: Dict[str, Dict[str, object]] = None,
    ) -> Tuple[List[ApiCaseModel], Dict[str, Set[str]]]:
        """拓扑排序 + 计算变量传递关系

        Returns:
            (排序后的用例列表, 变量传递映射 {case_id -> {可用变量名}})
        """
        sorted_cases = cls.resolve(cases)
        transfer_map: Dict[str, Set[str]] = {}

        # 上游 -> 下游变量传递
        upstream_vars: Dict[str, Set[str]] = {}
        for case in sorted_cases:
            transfer_map[case.case_id] = set()
            if case.depends_on and case.depends_on in upstream_vars:
                # 下游可访问上游提取的变量
                transfer_map[case.case_id] = upstream_vars[case.depends_on].copy()
            # 当前用例提取的变量 -> 累加到上游集合
            if case.extract:
                current_vars = set(case.extract.keys())
                upstream_vars[case.case_id] = transfer_map[case.case_id] | current_vars

        return sorted_cases, transfer_map