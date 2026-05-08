# -*- coding: utf-8 -*-
from __future__ import annotations

"""
석고보드 절단 최적화 시스템
- 건물 전체 벽에 석고보드를 최적 배치하여 로스율 최소화
- 규격: 900x1800mm, 스터드 간격 450mm
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dataclasses import dataclass, field
from typing import Optional
import math

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
BW = 900    # 보드 너비 (mm)
BH = 1800   # 보드 높이 (mm)
STUD = 450  # 스터드 간격 (mm)
MIN_REUSE = 450  # 재사용 최소 치수 (mm)


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────
@dataclass
class Wall:
    wall_id: str
    space_id: str
    floor_id: str
    L: int   # 벽 길이 (mm)
    H: int   # 벽 높이 (mm)
    ow: int = 0  # 개구부 너비
    oh: int = 0  # 개구부 높이
    ox: int = 0  # 개구부 x좌표 (벽 왼쪽 끝에서)
    oy: int = 0  # 개구부 y좌표 (바닥에서)


@dataclass
class Piece:
    """배치된 조각 하나"""
    x: int
    y: int
    w: int
    h: int
    kind: str       # 'full' | 'cut' | 'reused'
    source_wall: str = ""
    has_opening: bool = False


@dataclass
class ReusePiece:
    """재사용 가능한 자투리 조각"""
    w: int
    h: int
    space_id: str
    floor_id: str
    source_wall: str


@dataclass
class WallResult:
    wall_id: str
    boards_used: float
    loss_rate: float
    layout: str
    pieces: list[Piece] = field(default_factory=list)
    reuse_in: int = 0
    reuse_out: int = 0


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def snap_up(v: int, step: int) -> int:
    return math.ceil(v / step) * step


def opening_x_range(wall: Wall):
    if wall.ow == 0:
        return None
    return (wall.ox, wall.ox + wall.ow)


def opening_y_range(wall: Wall):
    if wall.oh == 0:
        return None
    return (wall.oy, wall.oy + wall.oh)


def piece_overlaps_opening(px, pw, py, ph, wall: Wall) -> bool:
    if wall.ow == 0:
        return False
    ox1, ox2 = wall.ox, wall.ox + wall.ow
    oy1, oy2 = wall.oy, wall.oy + wall.oh
    return px < ox2 and (px + pw) > ox1 and py < oy2 and (py + ph) > oy1


def effective_area(px, pw, py, ph, wall: Wall) -> int:
    total = pw * ph
    if wall.ow == 0:
        return total
    ox1, ox2 = wall.ox, wall.ox + wall.ow
    oy1, oy2 = wall.oy, wall.oy + wall.oh
    inter_w = max(0, min(px + pw, ox2) - max(px, ox1))
    inter_h = max(0, min(py + ph, oy2) - max(py, oy1))
    return total - inter_w * inter_h


# ─────────────────────────────────────────────
# 열(x방향) 계획 수립
# ─────────────────────────────────────────────
def build_column_plan(wall: Wall, x_start: int) -> list[dict]:
    columns = []
    x = x_start
    ox_range = opening_x_range(wall)

    while x < wall.L:
        ideal_right = x + BW
        if ox_range:
            ox1, ox2 = ox_range
            if x < ox1 < ideal_right:
                columns.append({'x': x, 'w': ox1 - x})
                x = ox1
                continue
            if x < ox2 < ideal_right:
                columns.append({'x': x, 'w': ox2 - x})
                x = ox2
                continue

        col_w = min(BW, wall.L - x)
        columns.append({'x': x, 'w': col_w})
        x += col_w

    return columns


def build_column_plan_from_opening(wall: Wall) -> list[dict]:
    if wall.ow == 0:
        return build_column_plan(wall, 0)
    ox1 = wall.ox
    if ox1 == 0:
        return build_column_plan(wall, 0)
    offset = ox1 % BW
    return build_column_plan(wall, offset)


# ─────────────────────────────────────────────
# 행(y방향) 계획 수립
# ─────────────────────────────────────────────
def get_row_starts_case_c(wall: Wall, col_x: int, col_w: int) -> list[dict]:
    rows = []
    oy_range = opening_y_range(wall)
    ox_range = opening_x_range(wall)

    col_overlaps_x = False
    if ox_range and col_w > 0:
        ox1, ox2 = ox_range
        col_overlaps_x = col_x < ox2 and (col_x + col_w) > ox1

    if not col_overlaps_x or not oy_range:
        y = 0
        while y < wall.H:
            h = min(BH, wall.H - y)
            rows.append({'y': y, 'h': h, 'in_opening': False})
            y += h
        return rows

    oy1, oy2 = oy_range

    y = 0
    while y < oy1:
        h = min(BH, oy1 - y)
        rows.append({'y': y, 'h': h, 'in_opening': False})
        y += h

    rows.append({'y': oy1, 'h': oy2 - oy1, 'in_opening': True})

    y = oy2
    while y < wall.H:
        h = min(BH, wall.H - y)
        rows.append({'y': y, 'h': h, 'in_opening': False})
        y += h

    return rows


def get_row_starts_case_d(wall: Wall, col_x: int, col_w: int) -> list[dict]:
    rows = []
    y = 0
    while y < wall.H:
        h = min(BH, wall.H - y)
        in_op = piece_overlaps_opening(col_x, col_w, y, h, wall)
        rows.append({'y': y, 'h': h, 'in_opening': in_op})
        y += h
    return rows


# ─────────────────────────────────────────────
# 단일 벽 배치 계산 (4가지 조합 AC/AD/BC/BD)
# ─────────────────────────────────────────────
def calc_wall_layout(wall: Wall, x_case: str, y_case: str) -> dict:
    if x_case == 'A':
        columns = build_column_plan(wall, 0)
    else:
        columns = build_column_plan_from_opening(wall)

    pieces: list[Piece] = []
    reuse_pieces: list[ReusePiece] = []
    board_area_used = 0
    actual_area = 0

    for col in columns:
        cx, cw = col['x'], col['w']

        if y_case == 'C':
            rows = get_row_starts_case_c(wall, cx, cw)
        else:
            rows = get_row_starts_case_d(wall, cx, cw)

        for row in rows:
            ry, rh = row['y'], row['h']
            in_op = row['in_opening']

            if in_op and y_case == 'C':
                continue

            overlaps = piece_overlaps_opening(cx, cw, ry, rh, wall)
            kind = 'full' if (cw == BW and rh == BH) else 'cut'
            pieces.append(Piece(x=cx, y=ry, w=cw, h=rh, kind=kind, has_opening=overlaps))

            used_h = snap_up(rh, BH) if rh <= BH else BH
            board_area_used += BW * min(used_h, BH)
            actual_area += effective_area(cx, cw, ry, rh, wall)

            scrap_w = BW - cw
            if scrap_w >= MIN_REUSE and rh >= MIN_REUSE:
                reuse_pieces.append(ReusePiece(
                    w=scrap_w, h=rh,
                    space_id=wall.space_id, floor_id=wall.floor_id, source_wall=wall.wall_id,
                ))
            scrap_h = BH - rh
            if scrap_h >= MIN_REUSE and cw >= MIN_REUSE:
                reuse_pieces.append(ReusePiece(
                    w=cw, h=scrap_h,
                    space_id=wall.space_id, floor_id=wall.floor_id, source_wall=wall.wall_id,
                ))

    return {
        'pieces': pieces,
        'board_area_used': board_area_used,
        'actual_area': actual_area,
        'reuse_pieces': reuse_pieces,
    }


# ─────────────────────────────────────────────
# HYBRID-X: 직사각형 영역 배치 (개구부 없는 순수 영역)
# ─────────────────────────────────────────────
def calc_region(
    ox_start: int, oy_start: int,
    region_w: int, region_h: int,
    board_w: int, board_h: int,
    space_id: str, floor_id: str, wall_id: str,
) -> dict:
    """
    개구부 없는 직사각형 영역에 board_w×board_h 방향으로 보드 배치.
      board_w=BW(900), board_h=BH(1800) → 세로(V)
      board_w=BH(1800), board_h=BW(900) → 가로(H, 90° 회전)
    """
    pieces: list[Piece] = []
    reuse_pieces: list[ReusePiece] = []
    board_area_used = 0
    actual_area = 0

    x = ox_start
    while x < ox_start + region_w:
        cw = min(board_w, (ox_start + region_w) - x)
        y = oy_start
        while y < oy_start + region_h:
            rh = min(board_h, (oy_start + region_h) - y)

            kind = 'full' if (cw == board_w and rh == board_h) else 'cut'
            pieces.append(Piece(x=x, y=y, w=cw, h=rh, kind=kind))

            # 보드 1장 소모 (방향과 무관하게 BW*BH = BH*BW = 1,620,000)
            board_area_used += board_w * board_h
            actual_area += cw * rh

            scrap_w = board_w - cw
            if scrap_w >= MIN_REUSE and rh >= MIN_REUSE:
                reuse_pieces.append(ReusePiece(
                    w=scrap_w, h=rh,
                    space_id=space_id, floor_id=floor_id, source_wall=wall_id,
                ))
            scrap_h = board_h - rh
            if scrap_h >= MIN_REUSE and cw >= MIN_REUSE:
                reuse_pieces.append(ReusePiece(
                    w=cw, h=scrap_h,
                    space_id=space_id, floor_id=floor_id, source_wall=wall_id,
                ))

            y += board_h
        x += board_w

    return {
        'pieces': pieces,
        'board_area_used': board_area_used,
        'actual_area': actual_area,
        'reuse_pieces': reuse_pieces,
    }


def _best_region(
    ox_start: int, oy_start: int,
    region_w: int, region_h: int,
    space_id: str, floor_id: str, wall_id: str,
) -> tuple[str, dict]:
    """V(세로 900×1800) vs H(가로 1800×900) 중 로스율 낮은 방향 선택."""
    v = calc_region(ox_start, oy_start, region_w, region_h,
                    BW, BH, space_id, floor_id, wall_id)
    h = calc_region(ox_start, oy_start, region_w, region_h,
                    BH, BW, space_id, floor_id, wall_id)

    def loss(r: dict) -> float:
        ba = r['board_area_used']
        return (ba - r['actual_area']) / ba if ba > 0 else 0.0

    return ('V', v) if loss(v) <= loss(h) else ('H', h)


# ─────────────────────────────────────────────
# HYBRID-X 레이아웃: x축 개구부 경계로 띠 분할
# ─────────────────────────────────────────────
def calc_hybrid_x_layout(wall: Wall) -> dict:
    """
    개구부 x경계(ox, ox+ow)로 벽을 수직 스트립으로 분할하고
    각 순수 영역에서 독립적으로 V/H 최적 방향 선택.

    분할 구조 (개구부 있을 때):
      ┌─────────┬──────┬──────────┐
      │  좌측   │  개  │  우측    │  ← 각각 V or H 독립 선택
      │  스트립 │  구  │  스트립  │
      │         │  부  │          │
      │         │  열  │          │
      │         │(위/아│          │
      │         │래 분│          │
      │         │ 리)  │          │
      └─────────┴──────┴──────────┘
    """
    sid, fid, wid = wall.space_id, wall.floor_id, wall.wall_id
    all_pieces: list[Piece] = []
    all_reuse: list[ReusePiece] = []
    total_board_area = 0
    total_actual_area = 0

    def add(sx: int, sy: int, sw: int, sh: int) -> None:
        nonlocal total_board_area, total_actual_area
        if sw <= 0 or sh <= 0:
            return
        _, res = _best_region(sx, sy, sw, sh, sid, fid, wid)
        all_pieces.extend(res['pieces'])
        all_reuse.extend(res['reuse_pieces'])
        total_board_area += res['board_area_used']
        total_actual_area += res['actual_area']

    if wall.ow == 0:
        # 개구부 없음: 전체 벽 단일 영역
        add(0, 0, wall.L, wall.H)
    else:
        ox1, ox2 = wall.ox, wall.ox + wall.ow
        oy1, oy2 = wall.oy, wall.oy + wall.oh

        # 개구부 왼쪽 스트립 (전체 높이)
        add(0, 0, ox1, wall.H)

        # 개구부 열: 개구부 아래 sub-region
        add(ox1, 0, ox2 - ox1, oy1)

        # 개구부 열: 개구부 위 sub-region
        add(ox1, oy2, ox2 - ox1, wall.H - oy2)

        # 개구부 오른쪽 스트립 (전체 높이)
        add(ox2, 0, wall.L - ox2, wall.H)

    return {
        'pieces': all_pieces,
        'board_area_used': total_board_area,
        'actual_area': total_actual_area,
        'reuse_pieces': all_reuse,
    }


# ─────────────────────────────────────────────
# 최적 레이아웃 선택 (AC/AD/BC/BD + HYBRID-X)
# ─────────────────────────────────────────────
def best_layout_for_wall(wall: Wall) -> tuple[str, dict]:
    """
    5가지 방법 모두 계산 후 로스율 최소 선택:
      AC / AD / BC / BD : 기존 4가지 조합
      HYBRID-X          : x축 띠 분할 + 영역별 V/H 독립 선택 (신규)
    """
    best_name = None
    best_result = None
    best_loss = float('inf')

    for x_case in ('A', 'B'):
        for y_case in ('C', 'D'):
            name = x_case + y_case
            result = calc_wall_layout(wall, x_case, y_case)
            ba = result['board_area_used']
            loss = (ba - result['actual_area']) / ba if ba > 0 else 0.0
            if loss < best_loss:
                best_loss = loss
                best_name = name
                best_result = result

    # HYBRID-X: x축 띠 분할 + 영역별 V/H 최적 선택
    hx = calc_hybrid_x_layout(wall)
    ba = hx['board_area_used']
    hx_loss = (ba - hx['actual_area']) / ba if ba > 0 else 0.0
    if hx_loss < best_loss:
        best_name = 'HYBRID-X'
        best_result = hx

    return best_name, best_result


# ─────────────────────────────────────────────
# 재사용 풀 관리
# ─────────────────────────────────────────────
class ReusePool:
    def __init__(self):
        self._pieces: list[ReusePiece] = []

    def push(self, piece: ReusePiece):
        self._pieces.append(piece)

    def consume(self, needed_w: int, needed_h: int,
                space_id: str, floor_id: str) -> Optional[ReusePiece]:
        def priority(p: ReusePiece) -> int:
            if p.space_id == space_id:
                return 0
            if p.floor_id == floor_id:
                return 1
            return 2

        candidates = [p for p in self._pieces if p.w >= needed_w and p.h >= needed_h]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (priority(p), p.w * p.h))
        chosen = candidates[0]
        self._pieces.remove(chosen)
        return chosen

    def __len__(self):
        return len(self._pieces)


# ─────────────────────────────────────────────
# 벽 처리 순서 결정
# ─────────────────────────────────────────────
def order_walls(walls: list[Wall], strategy: str) -> list[Wall]:
    def net_area(w: Wall):
        return w.L * w.H - w.ow * w.oh

    if strategy == 'large_first':
        return sorted(walls, key=net_area, reverse=True)
    elif strategy == 'small_first':
        return sorted(walls, key=net_area)
    else:
        return sorted(walls, key=lambda w: (w.floor_id, w.space_id, -net_area(w)))


# ─────────────────────────────────────────────
# 동일 타입 그룹핑
# ─────────────────────────────────────────────
def group_by_type(walls: list[Wall]) -> dict[tuple, list[Wall]]:
    groups: dict[tuple, list[Wall]] = {}
    for w in walls:
        key = (w.L, w.H, w.ow, w.oh, w.ox, w.oy)
        groups.setdefault(key, []).append(w)
    return groups


# ─────────────────────────────────────────────
# 메인 최적화 루프
# ─────────────────────────────────────────────
def optimize(walls: list[Wall], verbose: bool = True) -> dict:
    type_groups = group_by_type(walls)
    if verbose:
        print(f"[1단계] {len(walls)}개 벽 → {len(type_groups)}개 고유 타입")

    type_layout: dict[tuple, tuple[str, dict]] = {}
    for key, group in type_groups.items():
        rep = group[0]
        layout_name, layout_result = best_layout_for_wall(rep)
        type_layout[key] = (layout_name, layout_result)

    def total_loss_for_order(strategy: str) -> float:
        ordered = order_walls(walls, strategy)
        total_used = sum(type_layout[(w.L, w.H, w.ow, w.oh, w.ox, w.oy)][1]['board_area_used']
                         for w in ordered)
        total_actual = sum(type_layout[(w.L, w.H, w.ow, w.oh, w.ox, w.oy)][1]['actual_area']
                           for w in ordered)
        return (total_used - total_actual) / total_used if total_used > 0 else 0.0

    strategies = ['large_first', 'small_first', 'floor_space']
    strategy_losses = {s: total_loss_for_order(s) for s in strategies}
    best_strategy = min(strategy_losses, key=strategy_losses.get)

    if verbose:
        labels = {
            'large_first': 'A(큰 벽 먼저)',
            'small_first': 'B(작은 벽 먼저)',
            'floor_space': 'C(층→공간→큰 벽)',
        }
        print("[2단계] 처리 순서별 예상 로스율:")
        for s, loss in strategy_losses.items():
            marker = " ◀ 선택" if s == best_strategy else ""
            print(f"  {labels[s]}: {loss*100:.2f}%{marker}")

    ordered_walls = order_walls(walls, best_strategy)

    reuse_pool = ReusePool()
    wall_results: list[WallResult] = []
    total_board_area = 0
    total_actual_area = 0
    total_reuse_in = 0
    total_reuse_out = 0

    if verbose:
        print("\n[3~4단계] 벽별 배치 결과:")
        print(f"  {'벽ID':<8} {'레이아웃':<10} {'로스율':>7} {'재사용IN':>6} {'재사용OUT':>7}")
        print("  " + "-" * 50)

    for wall in ordered_walls:
        key = (wall.L, wall.H, wall.ow, wall.oh, wall.ox, wall.oy)
        layout_name, base_result = type_layout[key]

        pieces = []
        reuse_in_count = 0
        reuse_out_count = 0
        board_area_used = 0
        actual_area = 0

        for p in base_result['pieces']:
            candidate = reuse_pool.consume(p.w, p.h, wall.space_id, wall.floor_id)
            if candidate:
                pieces.append(Piece(
                    x=p.x, y=p.y, w=p.w, h=p.h,
                    kind='reused', source_wall=candidate.source_wall,
                    has_opening=p.has_opening,
                ))
                reuse_in_count += 1
                actual_area += effective_area(p.x, p.w, p.y, p.h, wall)
            else:
                pieces.append(p)
                board_area_used += BW * BH
                if p.w < BW or p.h < BH:
                    board_area_used -= BW * BH
                    board_area_used += BW * min(snap_up(p.h, BH), BH)
                actual_area += effective_area(p.x, p.w, p.y, p.h, wall)

        for rp in base_result['reuse_pieces']:
            reuse_pool.push(rp)
            reuse_out_count += 1

        loss_rate = (
            max(0.0, (board_area_used - actual_area) / board_area_used * 100)
            if board_area_used > 0 else 0.0
        )

        wr = WallResult(
            wall_id=wall.wall_id,
            boards_used=board_area_used / (BW * BH),
            loss_rate=loss_rate,
            layout=layout_name,
            pieces=pieces,
            reuse_in=reuse_in_count,
            reuse_out=reuse_out_count,
        )
        wall_results.append(wr)

        total_board_area += board_area_used
        total_actual_area += actual_area
        total_reuse_in += reuse_in_count
        total_reuse_out += reuse_out_count

        if verbose:
            print(f"  {wall.wall_id:<8} {layout_name:<10} {loss_rate:>6.1f}%  "
                  f"{reuse_in_count:>5}    {reuse_out_count:>6}")

    total_boards = sum(r.boards_used for r in wall_results)
    total_loss_rate = (
        (total_board_area - total_actual_area) / total_board_area * 100
        if total_board_area > 0 else 0.0
    )

    if verbose:
        print(f"\n[5단계] 최종 결과")
        print(f"  총 온장 수 (환산): {total_boards:.1f}장")
        print(f"  전체 로스율:       {total_loss_rate:.2f}%")
        print(f"  재사용 횟수:       {total_reuse_in}회")
        print(f"  자투리 생성 수:    {total_reuse_out}개")
        print(f"  남은 재사용 풀:    {len(reuse_pool)}개")

    return {
        "total_boards": round(total_boards, 2),
        "total_loss_rate": round(total_loss_rate, 2),
        "reuse_count": total_reuse_in,
        "reuse_generated": total_reuse_out,
        "order_strategy": best_strategy,
        "wall_results": [
            {
                "wall_id": r.wall_id,
                "boards_used": round(r.boards_used, 2),
                "loss_rate": round(r.loss_rate, 2),
                "layout": r.layout,
                "reuse_in": r.reuse_in,
                "reuse_out": r.reuse_out,
                "pieces": [
                    {
                        "x": p.x, "y": p.y,
                        "w": p.w, "h": p.h,
                        "kind": p.kind,
                        "source_wall": p.source_wall,
                        "has_opening": p.has_opening,
                    }
                    for p in r.pieces
                ],
            }
            for r in wall_results
        ],
    }


# ─────────────────────────────────────────────
# 예제 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    sample_walls = [
        Wall(wall_id="W001", space_id="SP001", floor_id="2F",
             L=3000, H=2800, ow=1000, oh=1200, ox=800, oy=900),
        Wall(wall_id="W002", space_id="SP001", floor_id="2F",
             L=3000, H=2800, ow=1000, oh=1200, ox=800, oy=900),  # W001과 동일 타입
        Wall(wall_id="W003", space_id="SP002", floor_id="2F",
             L=4500, H=2800, ow=0, oh=0, ox=0, oy=0),
        Wall(wall_id="W004", space_id="SP001", floor_id="3F",
             L=2700, H=2800, ow=900, oh=2100, ox=900, oy=0),
        Wall(wall_id="W005", space_id="SP003", floor_id="3F",
             L=1800, H=2800, ow=0, oh=0, ox=0, oy=0),
    ]

    result = optimize(sample_walls, verbose=True)

    print("\n─── 벽별 상세 (pieces 좌표) ───")
    for wr in result["wall_results"]:
        print(f"\n  [{wr['wall_id']}] layout={wr['layout']} loss={wr['loss_rate']}%")
        for p in wr["pieces"]:
            tag = f"[{p['kind']}]" + (" [개구부]" if p['has_opening'] else "")
            print(f"    ({p['x']},{p['y']}) {p['w']}×{p['h']}mm  {tag}")

    # HYBRID-X 단독 테스트: 개구부가 중간에 있는 벽
    print("\n─── HYBRID-X 단독 테스트 ───")
    print("벽: L=3000, H=2800, 개구부=(ox=800, ow=1000, oy=900, oh=1200)")
    w = sample_walls[0]
    hx = calc_hybrid_x_layout(w)
    ba = hx['board_area_used']
    loss = (ba - hx['actual_area']) / ba * 100 if ba > 0 else 0.0
    print(f"  보드 면적 소모: {ba:,}mm²  실사용: {hx['actual_area']:,}mm²  로스율: {loss:.2f}%")
    print(f"  조각 수: {len(hx['pieces'])}개")

    print("\n  영역별 분할 (x축 스트립):")
    print(f"    좌측 스트립: x=[0, 800), w=800, H=2800")
    print(f"    개구부 열 하단: x=[800, 1800), w=1000, h=900")
    print(f"    개구부 열 상단: x=[800, 1800), w=1000, h=700  (2800-900-1200=700)")
    print(f"    우측 스트립: x=[1800, 3000), w=1200, H=2800")

    for p in hx['pieces']:
        orient = "H" if p.w > BW or p.h < BH else "V"
        print(f"    ({p.x:>4},{p.y:>4}) {p.w:>4}×{p.h:>4}mm  [{p.kind}] {orient}")
