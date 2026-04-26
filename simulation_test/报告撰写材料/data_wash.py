from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable

import pandas as pd


RAW_DATA = """波长,功率(mw),半径/光斑(um),曝光时间,光斑等级
577,150,200,0.2ms,3
577,100,200,0.2ms,2-3
577,100,200,0.2ms,3
577,100,200,0.2ms,2-3
577,100,300,0.2ms,3
577,200,300,0.2ms,3
577,230,300,0.2ms,3
577,130,200,0.2ms,3
577,200,300,0.2ms,3
577,200,300,200ms,3
577,200,300,0.2ms,3
577,200,300,200ms,3
577,200,300,0.2ms,3
577,200,300,0.2ms,3
577,110,200,0.2ms,3
577,110,300,0.2ms,2-3
577,100-120,200,200ms,3
577,180-200,300,200ms,2-3
577,160-180,300,200ms,2-3
577,130,300,200ms,2-3
577,130,300,200ms,2-3
577,180,200,200ms,3
577,130-200,200,200ms,3
577,130-200,200,200ms,3
577,200,300,200ms,3
577,200,300,0.2ms,3
577,000,200,200ms,3
577,130,200,200ms,3
577,110,200,200ms,3
577,160,300,200ms,3
577,200,300,0.2ms,3
577,200,300,200ms,3
577,140,300,200ms,2-3
577,180,300,200ms,2-3
577,200,300,0.2ms,3
577,200,300,200ms,3
577,200,300,200ms,3
577,200,300,0.2ms,3
577,180,200,0.2ms,3
577,140,200,0.2ms,2-3
577,160,200,0.2ms,2-3
577,200,200,0.2ms,2-3
577,180,180,0.2ms,2-3
577,200,300,0.2ms,3
577,160,200,0.2ms,3
577,180,200,250ms,3
577,180,200,200ms,2-3
577,110,200,0.2ms,2-3
577,200,300,0.2ms,2
577,160,200,200ms,2-3
577,120,200,0.2ms,2-3
577,160,200,0.2ms,2-3
577,160,200,0.2ms,2-3
577,160,200,0.2ms,2-3
577,140,200,0.2ms,2-3"""

POWER_COL = "功率(mw)"
SPOT_COL = "半径/光斑(um)"
TIME_COL = "曝光时间"
LABEL_COL = "光斑等级"
WAVELENGTH_COL = "波长"


@dataclass(frozen=True)
class ConflictEdge:
    a: int
    b: int
    reason: str


def load_raw_dataframe(raw_text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(raw_text), dtype=str).fillna("")


def normalize_label(x: str) -> int:
    x = str(x).strip()
    if x == "2-3":
        return 2
    if x in {"2", "3"}:
        return int(x)
    raise ValueError(f"无法识别标签: {x!r}")


def normalize_power_text(x: str) -> str:
    x = str(x).strip()
    if "-" in x:
        lo, hi = [p.strip() for p in x.split("-", 1)]
        return f"{int(float(lo))}-{int(float(hi))}"
    return str(int(float(x)))


def normalize_spot_text(x: str) -> str:
    return str(int(float(str(x).strip())))


def normalize_time_text(x: str) -> str:
    x = str(x).strip().lower()
    if x == "0.2ms":
        return "200ms"
    if x.endswith("ms"):
        return f"{int(float(x[:-2]))}ms"
    return x


def basic_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    stats: dict[str, int] = {"raw_rows": len(df)}

    step1 = df.drop_duplicates().copy()
    stats["after_first_dedup"] = len(step1)

    step2 = step1.copy()
    step2[TIME_COL] = step2[TIME_COL].map(normalize_time_text)
    step2 = step2[~step2[POWER_COL].astype(str).str.strip().isin(["000", "0", "0.0"])]
    step2[POWER_COL] = step2[POWER_COL].map(normalize_power_text)
    step2[SPOT_COL] = step2[SPOT_COL].map(normalize_spot_text)
    step2[LABEL_COL] = step2[LABEL_COL].map(normalize_label)
    step2 = step2.drop_duplicates().reset_index(drop=True)
    stats["after_fix_and_second_dedup"] = len(step2)
    return step2, stats


def is_range_power(x: str) -> bool:
    return "-" in str(x)


def parse_point_row(row: pd.Series) -> dict[str, float | int | str]:
    return {
        "wave": str(row[WAVELENGTH_COL]),
        "power": float(row[POWER_COL]),
        "spot": float(row[SPOT_COL]),
        "time_ms": float(str(row[TIME_COL]).replace("ms", "")),
        "label": int(row[LABEL_COL]),
    }


def parse_range_row(row: pd.Series) -> dict[str, float | int | str]:
    power_lo, power_hi = [float(p) for p in str(row[POWER_COL]).split("-", 1)]
    spot = float(row[SPOT_COL])
    time_ms = float(str(row[TIME_COL]).replace("ms", ""))
    return {
        "wave": str(row[WAVELENGTH_COL]),
        "power_lo": power_lo,
        "power_hi": power_hi,
        "spot_lo": spot,
        "spot_hi": spot,
        "time_lo": time_ms,
        "time_hi": time_ms,
        "label": int(row[LABEL_COL]),
    }


def point_inside_range(point: pd.Series, rng: pd.Series) -> bool:
    p = parse_point_row(point)
    r = parse_range_row(rng)
    return (
        p["wave"] == r["wave"]
        and r["power_lo"] <= p["power"] <= r["power_hi"]
        and r["spot_lo"] <= p["spot"] <= r["spot_hi"]
        and r["time_lo"] <= p["time_ms"] <= r["time_hi"]
    )


def dominates_or_equal(a: dict[str, float | int | str], b: dict[str, float | int | str]) -> bool:
    """a 是否在参数上强于或等于 b：功率更大/时间更长/光斑更小。"""
    return (
        a["wave"] == b["wave"]
        and float(a["power"]) >= float(b["power"])
        and float(a["time_ms"]) >= float(b["time_ms"])
        and float(a["spot"]) <= float(b["spot"])
    )


def strictly_better_in_any_dimension(a: dict[str, float | int | str], b: dict[str, float | int | str]) -> bool:
    return (
        float(a["power"]) > float(b["power"])
        or float(a["time_ms"]) > float(b["time_ms"])
        or float(a["spot"]) < float(b["spot"])
    )


def point_conflict_reason(a: pd.Series, b: pd.Series) -> str | None:
    pa = parse_point_row(a)
    pb = parse_point_row(b)
    if pa["wave"] != pb["wave"]:
        return None

    # 同一参数组合但标签不同，直接冲突
    if (
        pa["power"] == pb["power"]
        and pa["spot"] == pb["spot"]
        and pa["time_ms"] == pb["time_ms"]
        and pa["label"] != pb["label"]
    ):
        return "同一参数组合标签冲突"

    # 最宽口径单调性：A 参数不优于 B，但标签更高；或者反过来
    if dominates_or_equal(pa, pb) and strictly_better_in_any_dimension(pa, pb):
        if pa["label"] < pb["label"]:
            return "全局单调性冲突"
    if dominates_or_equal(pb, pa) and strictly_better_in_any_dimension(pb, pa):
        if pb["label"] < pa["label"]:
            return "全局单调性冲突"

    return None


def build_point_conflicts(points_df: pd.DataFrame) -> list[ConflictEdge]:
    edges: list[ConflictEdge] = []
    for i in range(len(points_df)):
        for j in range(i + 1, len(points_df)):
            reason = point_conflict_reason(points_df.iloc[i], points_df.iloc[j])
            if reason:
                edges.append(ConflictEdge(i, j, reason))
    return edges


def find_point_range_conflicts(points_df: pd.DataFrame, ranges_df: pd.DataFrame) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for pi in range(len(points_df)):
        p = points_df.iloc[pi]
        for ri in range(len(ranges_df)):
            r = ranges_df.iloc[ri]
            if point_inside_range(p, r) and int(p[LABEL_COL]) != int(r[LABEL_COL]):
                out.setdefault(pi, []).append(
                    f"落入范围数据#{ri} 内且标签冲突(点={int(p[LABEL_COL])}, 范围={int(r[LABEL_COL])})"
                )
    return out


def connected_components(n: int, edges: Iterable[ConflictEdge]) -> list[list[int]]:
    adj = {i: set() for i in range(n)}
    for e in edges:
        adj[e.a].add(e.b)
        adj[e.b].add(e.a)

    seen: set[int] = set()
    comps: list[list[int]] = []
    for start in range(n):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        comp: list[int] = []
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        comps.append(sorted(comp))
    return comps


def strict_strategy(points_df: pd.DataFrame, ranges_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    point_range_conflicts = find_point_range_conflicts(points_df, ranges_df)
    point_conflicts = build_point_conflicts(points_df)

    remove_points = set(point_range_conflicts.keys())
    for e in point_conflicts:
        remove_points.add(e.a)
        remove_points.add(e.b)

    logs: list[dict[str, object]] = []
    for idx in sorted(remove_points):
        row = points_df.iloc[idx].to_dict()
        reasons = list(point_range_conflicts.get(idx, []))
        reasons.extend([e.reason for e in point_conflicts if e.a == idx or e.b == idx])
        row["删除原因"] = "；".join(sorted(set(reasons)))
        row["删除策略"] = "严格策略"
        logs.append(row)

    kept_points = points_df.drop(index=list(remove_points)).reset_index(drop=True)
    removed_df = pd.DataFrame(logs)
    return kept_points, ranges_df.reset_index(drop=True), removed_df


def choose_balanced_subset(points_df: pd.DataFrame, ranges_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # 范围 vs 单点：优先删单点
    point_range_conflicts = find_point_range_conflicts(points_df, ranges_df)
    forced_remove_original = set(point_range_conflicts.keys())

    survivor_points = points_df.drop(index=list(forced_remove_original)).reset_index(drop=True)
    survivor_to_original = [i for i in range(len(points_df)) if i not in forced_remove_original]
    edges = build_point_conflicts(survivor_points)
    edge_set = {(min(e.a, e.b), max(e.a, e.b)) for e in edges}

    # 全局类别平衡：先最大化保留数量，再最小化 |2级-3级|
    base_count_2 = int((ranges_df[LABEL_COL] == 2).sum())
    base_count_3 = int((ranges_df[LABEL_COL] == 3).sum())

    def component_solutions(comp: list[int]) -> list[tuple[set[int], int, int]]:
        comp = sorted(comp)
        comp_edges = {(u, v) for (u, v) in edge_set if u in comp and v in comp}
        best_size = -1
        sols: list[tuple[set[int], int, int]] = []
        n = len(comp)
        for mask in range(1 << n):
            chosen = {comp[k] for k in range(n) if (mask >> k) & 1}
            ok = True
            for u, v in comp_edges:
                if u in chosen and v in chosen:
                    ok = False
                    break
            if not ok:
                continue
            size = len(chosen)
            if size < best_size:
                continue
            c2 = int((survivor_points.loc[list(chosen), LABEL_COL] == 2).sum()) if chosen else 0
            c3 = int((survivor_points.loc[list(chosen), LABEL_COL] == 3).sum()) if chosen else 0
            if size > best_size:
                best_size = size
                sols = [(chosen, c2, c3)]
            else:
                sols.append((chosen, c2, c3))
        return sols

    all_comp_solutions = [component_solutions(comp) for comp in connected_components(len(survivor_points), edges)]

    best_choice: set[int] = set()
    best_score: tuple[int, int, int] | None = None

    def dfs(ci: int, current_choice: set[int], c2: int, c3: int) -> None:
        nonlocal best_choice, best_score
        if ci == len(all_comp_solutions):
            total_kept = len(current_choice)
            total_2 = base_count_2 + c2
            total_3 = base_count_3 + c3
            score = (total_kept, -abs(total_2 - total_3), -abs(c2 - c3))
            if best_score is None or score > best_score:
                best_score = score
                best_choice = set(current_choice)
            return

        for chosen, add2, add3 in all_comp_solutions[ci]:
            dfs(ci + 1, current_choice | chosen, c2 + add2, c3 + add3)

    dfs(0, set(), 0, 0)

    remove_in_survivor = set(range(len(survivor_points))) - best_choice
    remove_original = set(forced_remove_original) | {survivor_to_original[i] for i in remove_in_survivor}

    logs: list[dict[str, object]] = []
    for idx in sorted(remove_original):
        row = points_df.iloc[idx].to_dict()
        reasons = list(point_range_conflicts.get(idx, []))
        if idx not in forced_remove_original:
            survivor_idx = survivor_to_original.index(idx)
            related = [e.reason for e in edges if e.a == survivor_idx or e.b == survivor_idx]
            reasons.append("为解除全局单调性冲突并尽量保持类别平衡而删除")
            reasons.extend(sorted(set(related)))
        row["删除原因"] = "；".join(sorted(set(reasons)))
        row["删除策略"] = "放宽策略"
        logs.append(row)

    kept_points = points_df.drop(index=list(remove_original)).reset_index(drop=True)
    removed_df = pd.DataFrame(logs)
    return kept_points, ranges_df.reset_index(drop=True), removed_df


def summarize(name: str, points_df: pd.DataFrame, ranges_df: pd.DataFrame) -> None:
    total = len(points_df) + len(ranges_df)
    count2 = int((points_df[LABEL_COL] == 2).sum() + (ranges_df[LABEL_COL] == 2).sum())
    count3 = int((points_df[LABEL_COL] == 3).sum() + (ranges_df[LABEL_COL] == 3).sum())
    print(f"\n--- {name} ---")
    print(f"单点数据数量: {len(points_df)}")
    print(f"范围数据数量: {len(ranges_df)}")
    print(f"总数量: {total}")
    print(f"2级数量: {count2}")
    print(f"3级数量: {count3}")
    print(f"类别差值 |2级-3级|: {abs(count2 - count3)}")


if __name__ == "__main__":
    raw_df = load_raw_dataframe(RAW_DATA)
    cleaned_df, stats = basic_clean(raw_df)

    print(f"原始数据条数: {stats['raw_rows']}")
    print(f"合并重复项后剩余: {stats['after_first_dedup']}")
    print(f"修复错误并二次去重后剩余: {stats['after_fix_and_second_dedup']}")

    is_range = cleaned_df[POWER_COL].map(is_range_power)
    points_df = cleaned_df.loc[~is_range].reset_index(drop=True)
    ranges_df = cleaned_df.loc[is_range].reset_index(drop=True)

    strict_points, strict_ranges, strict_removed = strict_strategy(points_df, ranges_df)
    summarize("策略1：一旦冲突，删除所有涉及冲突的数据", strict_points, strict_ranges)

    relaxed_points, relaxed_ranges, relaxed_removed = choose_balanced_subset(points_df, ranges_df)
    summarize("策略2：冲突对中保留其一，并尽量保持类别平衡", relaxed_points, relaxed_ranges)

    final_df = pd.concat([relaxed_points, relaxed_ranges], ignore_index=True)

    cleaned_df.to_csv("step2_after_basic_clean.csv", index=False, encoding="utf-8-sig")
    strict_points.to_csv("strict_points.csv", index=False, encoding="utf-8-sig")
    strict_ranges.to_csv("strict_ranges.csv", index=False, encoding="utf-8-sig")
    strict_removed.to_csv("strict_removed_log.csv", index=False, encoding="utf-8-sig")
    relaxed_points.to_csv("relaxed_points.csv", index=False, encoding="utf-8-sig")
    relaxed_ranges.to_csv("relaxed_ranges.csv", index=False, encoding="utf-8-sig")
    relaxed_removed.to_csv("relaxed_removed_log.csv", index=False, encoding="utf-8-sig")
    final_df.to_csv("final_cleaned_logic2.csv", index=False, encoding="utf-8-sig")

    print("\n最终采用策略2，输出文件:")
    print("- step2_after_basic_clean.csv")
    print("- strict_points.csv / strict_ranges.csv / strict_removed_log.csv")
    print("- relaxed_points.csv / relaxed_ranges.csv / relaxed_removed_log.csv")
    print("- final_cleaned_logic2.csv")
