"""Wick 缩并图 QC 可视化（整合 lqcddb autowick.plot_figure_wick）。

对 wick_contraction 产出的 result_dict 画缩并示意图：夸克节点、传播子
箭头、γ 矩阵虚线、束缚态分隔与时间轴，全部视觉参数随图复杂度自适应。
2pt/3pt/4pt+ 通用。纯 matplotlib，无物理计算。
"""
from typing import Literal

import matplotlib
matplotlib.use('AGG')
import numpy as np
import matplotlib.patches as patches
import matplotlib.pyplot as plt


def plot_figure_wick(result_dict, diagram_index=0, Cpt:Literal['2pt', '3pt', '4pt']='2pt', plot_text:Literal[True, False] = True):

    """
    **Wick contraction diagram** — fully general for 2pt/3pt/4pt+.
    All visual parameters scale automatically with diagram complexity.
    """

    # ── Pre-compute structure to determine scale ───────────────────
    quark_pos  = result_dict['quark_pos']
    gamma_pos  = result_dict['gamma_pos']
    V_info     = result_dict['V']
    sign       = result_dict['result_sign'][diagram_index]
    peram_list = result_dict['peram'][diagram_index]
    cur_diagram = result_dict['result_indx'][diagram_index][0]
    cur_name    = result_dict['result_name'][diagram_index][0]
    sep_pos     = result_dict['sep_pos']

    is_2pt = (Cpt == '2pt')

    # ── Region intervals ───────────────────────────────────────────
    sorted_sep = sorted(sep_pos)
    intervals = [(sorted_sep[i], sorted_sep[i + 1])
                 for i in range(0, len(sorted_sep), 2)]
    n_regions = len(intervals)

    num_source_intervals = len([0 for x in result_dict['source_operators'] if x == '|']) // 2
    num_sink_intervals   = len([0 for x in result_dict['sink_operators']   if x == '|']) // 2
    n_cur = max(0, n_regions - num_source_intervals - num_sink_intervals)

    # ── Classify quarks into regions ───────────────────────────────
    src_quarks = []
    snk_quarks = []
    cur_quarks = [[] for _ in range(n_cur)]

    for (idx, qtype, label) in quark_pos:
        for ri, (low, high) in enumerate(intervals):
            if low <= idx <= high:
                if ri < num_sink_intervals:
                    snk_quarks.append((idx, qtype, label))
                elif ri >= n_regions - num_source_intervals:
                    src_quarks.append((idx, qtype, label))
                else:
                    cur_quarks[ri - num_sink_intervals].append((idx, qtype, label))
                break

    src_quarks.sort(key=lambda x: x[0])
    snk_quarks.sort(key=lambda x: x[0])
    for cq in cur_quarks:
        cq.sort(key=lambda x: x[0])

    # ── Scale factor — derived from diagram complexity ─────────────
    n_quarks = len(quark_pos)
    # More quarks / more regions → smaller base elements, but bounded
    complexity = max(n_quarks, 6) * (1 + 0.15 * (n_regions - 1))
    scale = max(0.75, min(1.0, 8.0 / complexity))

    # All visual dimensions scale together
    # ── 自适应视觉参数（全部乘以 scale 以适配不同复杂度的图）──────────────

    # 空间布局
    RAD       = 0.42 * scale   # 夸克节点圆的半径
    DY        = 1.6  * scale   # 同一区域内相邻夸克的纵向间距
    PAD       = 0.8  * scale   # 区域背景矩形在圆外的内边距
    SHRINK    = RAD             # 箭头端点收缩量，等于圆半径（保证箭头落在圆边界上）

    # 线宽
    LW_NODE   = 2.2 * scale   # 夸克圆的描边线宽
    LW_ARROW  = 3.0 * scale   # 传播子箭头线宽
    LW_GAMMA  = 2.5 * scale   # Gamma 矩阵虚线线宽
    LW_SEP    = 2.0 * scale   # 束缚态粒子分隔虚线线宽
    LW_BG     = 1.2 * scale   # 区域背景矩形边框线宽
    LW_TIME   = 3.0 * scale   # 时间方向箭头线宽
    LW_LEGEND = 3.0 * scale   # 图例中线条线宽

    # 箭头头部
    MUT_SCALE = 22  * scale   # 箭头头部大小（mutation_scale）

    # 字号
    FS_TITLE  = 17  * scale   # 顶部标题字号
    FS_REGION = 14  * scale   # 区域标签（Sink/Source/Current）字号
    FS_LABEL  = 10  * scale   # 夸克编号标签（如 [ab] S 1）字号
    FS_NODE   = 14  * scale   # 圆内夸克字母字号（u, d, ū 等）
    FS_GAMMA  = 13  * scale   # Gamma 矩阵标签字号
    FS_VERTEX = 13  * scale   # 顶点标签字号
    FS_TIME   = 13  * scale   # 时间方向文字字号
    FS_LEGEND = 9.5 * scale   # 图例文字字号
    FS_LEG_T  = 11  * scale   # 图例标题字号
    FS_INFO   = 10  * scale   # 左下角信息文字字号

    # 偏移量
    TEXT_OFF   = 0.25 * scale  # 夸克编号标签相对于圆心上方的偏移量
    TEXT_ASC   = 0.20 * scale  # 文字上沿的额外高度（用于分隔线避让计算）
    TITLE_PAD  = 18  * scale   # 标题与图的间距
    LEGEND_OFF = 1.01          # 图例横向偏移（相对坐标，无需缩放）


    # ── Figure size scales with content ────────────────────────────
    fig_w = 25 * scale
    fig_h = (10 + 2 * n_quarks / 5) * scale
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.set_aspect('equal')
    ax.axis('off')

    # ── letter → (quark_type, operator_index) ──────────────────────
    letter_to_quark = {}
    for (idx, qtype, label) in quark_pos:
        for ch in label:
            letter_to_quark[ch] = (qtype, idx)

    def get_region(idx):
        for low, high in intervals:
            if low <= idx <= high:
                return (low, high)
        return None

    # ── Colour palette ─────────────────────────────────────────────
    QC = {
        'u': '#3498DB',  'd': '#E74C3C',  's': '#2ECC71',
        'c': '#9B59B6',  'b': '#F39C12',  't': '#1ABC9C',
        'u^d': '#2471A3', 'd^d': '#CB4335', 's^d': '#1E8449',
        'c^d': '#7D3C98', 'b^d': '#D4AC0D', 't^d': '#17A589',
    }

    # ── Layout — fully dynamic x positions ─────────────────────────
    REGION_GAP = 10.0 * scale

    if is_2pt:
        SNK_X = 3.5 * scale
        SRC_X = SNK_X + REGION_GAP
        CUR_XS = []
    else:
        SNK_X = 2.5 * scale
        SRC_X = SNK_X + REGION_GAP
        if n_cur == 0:
            CUR_XS = []
        elif n_cur == 1:
            CUR_XS = [(SNK_X + SRC_X) / 2]
        else:
            CUR_XS = [SNK_X + (i + 1) * REGION_GAP / (n_cur + 1)
                      for i in range(n_cur)]

    # ── y positions ────────────────────────────────────────────────
    src_ys = [i * DY for i in range(len(src_quarks))]
    snk_ys = [i * DY for i in range(len(snk_quarks))]
    cur_yss = [[i * DY for i in range(len(cq))] for cq in cur_quarks]

    base_h = max(
        (src_ys[-1] + RAD) if src_ys else 0,
        (snk_ys[-1] + RAD) if snk_ys else 0)

    if not is_2pt:
        for ci in range(n_cur):
            offset = base_h + 2.0 * scale + ci * (DY * 2.5)
            cur_yss[ci] = [offset + i * DY for i in range(len(cur_quarks[ci]))]

    all_ys = src_ys + snk_ys
    for cys in cur_yss:
        all_ys += cys
    total_h = max(all_ys) + RAD + 1.0 * scale if all_ys else 3.0 * scale

    ymin = -2.5 * scale
    ymax = total_h + 1.5 * scale
    ax.set_xlim(-1 * scale, SRC_X + 3.0 * scale)
    ax.set_ylim(ymin, ymax)

    # ── Region backgrounds ─────────────────────────────────────────
    region_colors = [('#E8F8F5', 'Sink')] + \
                    [('#FEF9E7', f'Current {i+1}') for i in range(n_cur)] + \
                    [('#FDEDEC', 'Source')]

    for ri, (qx, qlist) in enumerate(
            [(SNK_X, src_quarks)] +
            [(CUR_XS[i], cur_quarks[i]) for i in range(n_cur)] +
            [(SRC_X, snk_quarks)]):
        if not qlist:
            continue
        ys = [snk_ys, *cur_yss, src_ys][ri]
        top = ys[-1] + RAD + PAD
        bot = ys[0]  - RAD - PAD
        h = top - bot
        color, label = region_colors[ri]
        ax.add_patch(patches.FancyBboxPatch(
            (qx - RAD - PAD, bot), 2 * (RAD + PAD), h,
            boxstyle='round,pad=0.2', facecolor=color,
            edgecolor='#BDC3C7', lw=LW_BG, alpha=0.45, zorder=0))
        ax.text(qx, top + 0.15 * scale, label,
                ha='center', va='bottom', fontsize=FS_REGION,
                fontweight='bold', color='#2C3E50', zorder=10)

    # ── Time arrow ─────────────────────────────────────────────────
    time_y = ymin + 0.3 * scale
    ax.annotate('', xy=(SRC_X + 1.5 * scale, time_y),
                xytext=(SNK_X - 1.5 * scale, time_y),
                arrowprops=dict(arrowstyle='<-', color='#2C3E50',
                                lw=LW_TIME, mutation_scale=20 * scale))
    ax.text((SNK_X + SRC_X) / 2, time_y - 0.45 * scale,
            'Time Direction  (sink <- Source)',
            ha='center', va='top', fontsize=FS_TIME,
            fontstyle='italic', fontweight='bold', color='#2C3E50')

    # ── Particle separator lines ───────────────────────────────────
    def get_particle_intervals(operators):
        sep_positions = [i for i, op in enumerate(operators) if op == '|']
        return [(sep_positions[i], sep_positions[i + 1])
                for i in range(0, len(sep_positions), 2)]

    source_particle_intervals = get_particle_intervals(result_dict['source_operators'])
    sink_particle_intervals   = get_particle_intervals(result_dict['sink_operators'])

    sink_offset    = 0
    curr_offset    = len(result_dict['sink_operators'])
    source_offset  = curr_offset + len(result_dict['curr_operators'])

    def draw_particle_separator_lines(quarks, ys, region_x, particle_intervals, offset=0):
        if len(quarks) <= 1:
            return

        particle_groups = []
        for p_low, p_high in particle_intervals:
            abs_low  = p_low + offset
            abs_high = p_high + offset
            group = [(q_idx, q_y) for (q_idx, _, _), q_y in zip(quarks, ys)
                     if abs_low <= q_idx <= abs_high]
            if group:
                group.sort(key=lambda x: x[1])
                particle_groups.append(group)

        for i in range(len(particle_groups) - 1):
            last_of_current  = particle_groups[i][-1][1]
            first_of_next    = particle_groups[i + 1][0][1]

            lower_text_top    = last_of_current + RAD + TEXT_OFF + TEXT_ASC
            upper_circle_bot  = first_of_next - RAD
            separator_y       = (lower_text_top + upper_circle_bot) / 2.0

            x_left  = region_x - RAD - PAD + 0.1 * scale
            x_right = region_x + RAD + PAD - 0.1 * scale
            ax.plot([x_left, x_right], [separator_y, separator_y],
                    color='#2C3E50', lw=LW_SEP, ls='--', alpha=0.6, zorder=1)

    draw_particle_separator_lines(src_quarks, src_ys, SRC_X,
                                  source_particle_intervals, offset=source_offset)
    draw_particle_separator_lines(snk_quarks, snk_ys, SNK_X,
                                  sink_particle_intervals, offset=sink_offset)

    # ── Helper: position by operator index ─────────────────────────
    def gq(qidx):
        for i, (idx, _, _) in enumerate(src_quarks):
            if idx == qidx:
                return SRC_X, src_ys[i]
        for ci, cq in enumerate(cur_quarks):
            for i, (idx, _, _) in enumerate(cq):
                if idx == qidx:
                    return CUR_XS[ci], cur_yss[ci][i]
        for i, (idx, _, _) in enumerate(snk_quarks):
            if idx == qidx:
                return SNK_X, snk_ys[i]
        return None, None

    # ── Draw quark nodes ───────────────────────────────────────────
    def display_name(qtype):
        if '^d' in qtype:
            base = qtype.replace('^d', '')
            return r'$\bar{' + base + '}$'
        return qtype

    def draw_node(cx, cy, qtype, lbl, rlabel, ni):
        c = QC.get(qtype, '#95A5A6')
        ax.add_patch(plt.Circle((cx, cy), RAD, color=c,
                                ec='#2C3E50', lw=LW_NODE, zorder=5))
        ax.text(cx, cy, display_name(qtype),
                ha='center', va='center',
                fontsize=FS_NODE, fontweight='bold', color='white', zorder=6)
        ax.text(cx, cy + RAD + TEXT_OFF, f'[{lbl}]  {rlabel} {ni+1}',
                ha='center', va='bottom', fontsize=FS_LABEL,
                color='#5D6D7E', zorder=6)

    for i, (idx, qt, lb) in enumerate(src_quarks):
        draw_node(SRC_X, src_ys[i], qt, lb, 'S', i)
    for ci, cq in enumerate(cur_quarks):
        for i, (idx, qt, lb) in enumerate(cq):
            draw_node(CUR_XS[ci], cur_yss[ci][i], qt, lb, f'C{ci+1}', i)
    for i, (idx, qt, lb) in enumerate(snk_quarks):
        draw_node(SNK_X, snk_ys[i], qt, lb, 'K', i)

    # ── Gamma-matrix dashed lines + Vertex labels ──────────────────
    if plot_text:
        for _, gname, gidx, _ in gamma_pos:
            if len(gidx) < 2:
                continue
            i1 = letter_to_quark.get(gidx[0])
            i2 = letter_to_quark.get(gidx[1])
            if i1 is None or i2 is None:
                continue
            x1, y1 = gq(i1[1])
            x2, y2 = gq(i2[1])
            if x1 is None or x2 is None:
                continue

            r1, r2 = get_region(i1[1]), get_region(i2[1])
            same_region = (r1 == r2)

            ax.plot([x1, x2], [y1, y2], '--', color='#E67E22',
                    lw=LW_GAMMA, alpha=0.85, zorder=2)

            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if same_region:
                mid_region_x = (SNK_X + SRC_X) / 2
                dx = -1.6 * scale if x1 < mid_region_x else 1.6 * scale
            else:
                dx = 1.0 * scale
                my += 0.55 * scale

            parts = gname.replace('gamma_', '').split('_')
            subscript = '|'.join(parts)
            label = r'$\Gamma_{\mathrm{%s}}^{\mathrm{%s}}$' % (subscript, gidx)

            ax.text(mx + dx, my, label,
                    ha='center', va='center', fontsize=FS_GAMMA,
                    fontweight='bold', color='#D35400',
                    bbox=dict(boxstyle='round,pad=0.3', fc='#FFF3E0',
                              ec='#E67E22', alpha=0.95), zorder=8)

        VC = {'VVV': '#C0392B', 'VDV': '#8E44AD'}
        for _, vn, vi, _ in V_info:
            vt = 'VVV' if 'VVV' in vn else 'VDV'
            col = VC[vt]
            pts = []
            for l in vi:
                info = letter_to_quark.get(l)
                if info is not None:
                    xy = gq(info[1])
                    if xy[0] is not None:
                        pts.append(xy)
            if not pts:
                continue
            cx = np.mean([p[0] for p in pts])
            if vt == 'VDV':
                cy = pts[1][1]
            else:
                cy = np.mean([p[1] for p in pts])

            mid_region_x = (SNK_X + SRC_X) / 2
            if cx < mid_region_x - 1 * scale:
                dx = -1.6 * scale
            elif cx > mid_region_x + 1 * scale:
                dx = 1.6 * scale
            else:
                dx = 1.5 * scale

            ax.text(cx + dx, cy, r'$\mathrm{%s}^{\mathrm{%s}}$' % (vn, vi),
                    ha='center', va='center', fontsize=FS_VERTEX,
                    fontweight='bold', color=col,
                    bbox=dict(boxstyle='round,pad=0.25', fc='#FDEDEC',
                              ec=col, alpha=0.95), zorder=8)
    # ── Build propagator list ──────────────────────────────────────
    quark_propagators = []
    for p in peram_list:
        pstr = p[3]
        src_l = (pstr[1], pstr[3])
        snk_l = (pstr[0], pstr[2])
        si = letter_to_quark.get(src_l[0])
        ki = letter_to_quark.get(snk_l[0])
        if si is None or ki is None:
            continue
        quark_propagators.append(dict(
            src_idx=si[1], snk_idx=ki[1],
            src_qtype=si[0], snk_qtype=ki[0]))
        
    # ── Propagators — arrows land on circle boundaries ─────────────
    PC = ['#2980B9', '#8E44AD', '#D35400', '#27AE60',
          '#C0392B', '#16A085', '#7F8C8D', '#F1C40F']

    for pi, qp in enumerate(quark_propagators):
        col = PC[pi % len(PC)]
        sx, sy = gq(qp['src_idx'])
        kx, ky = gq(qp['snk_idx'])
        if sx is None or kx is None:
            continue

        dist = np.sqrt((kx - sx)**2 + (ky - sy)**2)
        if dist < 2 * RAD + 0.01 * scale:
            continue

        # Unit direction vector (source center → sink center)
        ux = (kx - sx) / dist
        uy = (ky - sy) / dist

        # Arrow endpoints on circle boundaries
        start_x = sx + RAD * ux
        start_y = sy + RAD * uy
        end_x   = kx - RAD * ux
        end_y   = ky - RAD * uy

        # Arc curvature direction
        if kx < SNK_X + 1 * scale and sx > SRC_X - 1 * scale:
            rad = -(0.20 + 0.06 * (pi % 3))
        else:
            rad = (0.20 + 0.06 * (pi % 3))

        ax.annotate('', xy=(end_x, end_y), xytext=(start_x, start_y),
                    arrowprops=dict(
                        arrowstyle='->', color=col,
                        lw=LW_ARROW, mutation_scale=MUT_SCALE,
                        connectionstyle=f'arc3,rad={rad}'),
                    zorder=3)

    # ── Legend ─────────────────────────────────────────────────────
    seen = sorted(set(qt for _, qt, _ in quark_pos),
                  key=lambda x: x.replace('^d', 'z'))
    items = [patches.Patch(fc=QC.get(q, '#95A5A6'), ec='#2C3E50',
                           label=display_name(q))
             for q in seen]
    items += [
        plt.Line2D([], [], color='#2980B9', lw=LW_LEGEND,
                   label='Perambulator'),
        plt.Line2D([], [], color='#E67E22', lw=LW_LEGEND * 0.67, ls='--',
                   label='Gamma matrix'),
        plt.Line2D([], [], color='#2C3E50', lw=LW_LEGEND * 0.67, ls='--',
                   label='Particle separator'),
    ]

    ax.legend(handles=items, loc='upper left',
              bbox_to_anchor=(LEGEND_OFF, 1.0),
              fontsize=FS_LEGEND, framealpha=0.9,
              title='Legend', title_fontsize=FS_LEG_T)

    # ── Info text ──────────────────────────────────────────────────
    idx_str = cur_diagram
    if len(idx_str) > 45:
        parts = idx_str.split(',')
        lines, line = [], ''
        for p in parts:
            if len(line) + len(p) + 1 > 45:
                lines.append(line.rstrip(','))
                line = p + ','
            else:
                line += p + ','
        if line:
            lines.append(line.rstrip(','))
        idx_str = '\n'.join(lines)

    comp_str = cur_name
    if len(comp_str) > 55:
        parts = comp_str.split(', ')
        lines, line = [], ''
        for p in parts:
            if len(line) + len(p) + 2 > 55:
                lines.append(line.rstrip(', '))
                line = p + ', '
            else:
                line += p + ', '
        if line:
            lines.append(line.rstrip(', '))
        comp_str = '\n'.join(lines)

    info_text = (
        f"Contraction indices:\n{idx_str}\n\n"
        f"Components:\n{comp_str}\n\n"
        f"Contraction sign: {sign:.1f}"
    )

    ax.text(0.95, 0.02, info_text,
            transform=ax.transAxes, fontsize=FS_INFO,
            va='bottom', ha='left', family='monospace',
            bbox=dict(boxstyle='round', fc='#F7F9F9',
                      ec='#BDC3C7', alpha=0.95))

    tag = '2-pt' if is_2pt else f'{n_regions}-pt'
    ax.set_title(f'Wick Contraction Diagram #{diagram_index}  '
                 f'({Cpt}, sign = {sign:.1f})',
                 fontsize=FS_TITLE, fontweight='bold', pad=TITLE_PAD)
    plt.tight_layout()

    return fig, ax
