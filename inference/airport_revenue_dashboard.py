#!/usr/bin/env python3
"""
Airport Analytics Dashboard — two tabs
  Tab 1: Airport Revenue    (catalog_claude.gold.gold_airport_revenue_summary)
  Tab 2: Airport Performance (catalog_claude.gold.gold_airport_performance)
"""

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
import dash
from dash import ctx, dcc, html, Input, Output
import plotly.graph_objects as go

# ── Databricks ────────────────────────────────────────────────────────────────

def _get_warehouse_id(client: WorkspaceClient) -> str:
    warehouses = list(client.warehouses.list())
    if not warehouses:
        raise RuntimeError("No SQL warehouses found.")
    running = [w for w in warehouses if w.state and w.state.value == "RUNNING"]
    return (running[0] if running else warehouses[0]).id


def _sql(client: WorkspaceClient, wh_id: str, stmt: str) -> pd.DataFrame:
    result = client.statement_execution.execute_statement(
        warehouse_id=wh_id, statement=stmt,
        catalog="catalog_claude", schema="gold", wait_timeout="30s",
    )
    if result.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"Query failed: {result.status.error}")
    cols = [c.name for c in result.manifest.schema.columns]
    return pd.DataFrame(result.result.data_array or [], columns=cols)


print("Connecting to Databricks…")
_client = WorkspaceClient()
_wh     = _get_warehouse_id(_client)

print("  Loading gold_airport_revenue_summary…")
DF = _sql(_client, _wh, """
    SELECT airport_name, city, country,
           total_bookings, total_revenue, avg_revenue_per_booking
    FROM catalog_claude.gold.gold_airport_revenue_summary ORDER BY airport_name
""")
for c in ("total_bookings", "total_revenue", "avg_revenue_per_booking"):
    DF[c] = pd.to_numeric(DF[c])

print("  Loading gold_airport_performance…")
DF_PERF = _sql(_client, _wh, """
    SELECT airport_name, city, country,
           total_flights, unique_passengers, total_bookings,
           total_revenue, avg_booking_value, max_booking_value, min_booking_value
    FROM catalog_claude.gold.gold_airport_performance ORDER BY airport_name
""")
for c in ("total_flights","unique_passengers","total_bookings",
          "total_revenue","avg_booking_value","max_booking_value","min_booking_value"):
    DF_PERF[c] = pd.to_numeric(DF_PERF[c])

DF_PERF["pax_per_flight"]  = DF_PERF["unique_passengers"] / DF_PERF["total_flights"]
DF_PERF["revenue_per_pax"] = DF_PERF["total_revenue"]     / DF_PERF["unique_passengers"]

print(f"  Revenue: {len(DF)} rows  |  Performance: {len(DF_PERF)} rows")

AIRPORTS      = sorted(DF["airport_name"].unique())
AIRPORTS_PERF = sorted(DF_PERF["airport_name"].unique())

# Consistent color per airport across both tabs
PALETTE   = ["#6366F1","#EC4899","#14B8A6","#F59E0B","#3B82F6",
             "#10B981","#F97316","#8B5CF6","#EF4444","#06B6D4"]
COLOR_MAP = {a: PALETTE[i % len(PALETTE)]
             for i, a in enumerate(sorted(set(AIRPORTS) | set(AIRPORTS_PERF)))}

# ── Theme ─────────────────────────────────────────────────────────────────────

DARK   = "#0F172A"
NAVY   = "#1E3A5F"
LIGHT  = "#F1F5F9"
CARD   = "#FFFFFF"
MUTED  = "#64748B"
BORDER = "#E2E8F0"
FONT   = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
SHADOW = "0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)"

CHART_BASE = dict(
    plot_bgcolor=CARD, paper_bgcolor=CARD,
    font={"family": FONT, "size": 12, "color": DARK},
    hoverlabel={"bgcolor": "#fff", "bordercolor": BORDER,
                "font": {"size": 12, "family": FONT}},
)

TAB_STYLE = {
    "padding": "13px 28px", "fontWeight": "600", "fontSize": "13px",
    "color": MUTED, "borderBottom": "2px solid transparent",
    "background": "transparent",
}
SEL_TAB_STYLE = {**TAB_STYLE, "color": DARK, "borderBottom": f"2px solid {NAVY}"}

CARD_WRAP = {"background": CARD, "borderRadius": "14px", "padding": "8px",
             "boxShadow": SHADOW, "flex": "1", "minWidth": "340px"}
BTN       = {"border": "none", "borderRadius": "8px", "padding": "9px 18px",
             "fontSize": "13px", "fontWeight": "600", "cursor": "pointer", "lineHeight": "1"}

# ── Shared UI helpers ─────────────────────────────────────────────────────────

def kpi_card(icon: str, label: str, value: str, accent: str, note: str = "") -> html.Div:
    return html.Div([
        html.Div(icon, style={
            "fontSize": "20px", "lineHeight": "1",
            "background": f"linear-gradient(135deg, {accent}18, {accent}35)",
            "color": accent, "borderRadius": "10px",
            "width": "44px", "height": "44px", "flexShrink": "0",
            "display": "flex", "alignItems": "center", "justifyContent": "center",
        }),
        html.Div([
            html.P(label, style={
                "margin": "0 0 2px", "fontSize": "10px", "fontWeight": "700",
                "color": MUTED, "textTransform": "uppercase", "letterSpacing": "0.8px",
            }),
            html.Div(value, style={
                "fontSize": "22px", "fontWeight": "800", "color": DARK,
                "letterSpacing": "-0.5px", "lineHeight": "1.1",
            }),
            html.P(note, style={"margin": "3px 0 0", "fontSize": "11px", "color": MUTED}),
        ]),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "14px",
        "background": CARD, "borderRadius": "14px",
        "padding": "18px 20px", "boxShadow": SHADOW,
        "flex": "1", "minWidth": "185px",
        "borderLeft": f"3px solid {accent}",
    })


def h_bar(df: pd.DataFrame, col: str, title: str, prefix: str = "") -> go.Figure:
    s      = df.sort_values(col)
    colors = [COLOR_MAP.get(a, PALETTE[0]) for a in s["airport_name"]]
    fig = go.Figure(go.Bar(
        y=s["airport_name"], x=s[col], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{prefix}{v:,.1f}" for v in s[col]],
        textposition="outside", textfont={"size": 10, "color": DARK},
        cliponaxis=False,
        hovertemplate=f"<b>%{{y}}</b><br>{title}: {prefix}%{{x:,.2f}}<extra></extra>",
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 13, "color": DARK}, "x": 0.01, "y": 0.98},
        xaxis=dict(range=[0, s[col].max() * 1.20], showgrid=True,
                   gridcolor="#F1F5F9", zeroline=False, tickfont={"size": 10}),
        yaxis=dict(showgrid=False, tickfont={"size": 10}),
        margin={"l": 8, "r": 72, "t": 44, "b": 14},
        height=max(280, len(df) * 44 + 80),
        showlegend=False,
        **CHART_BASE,
    )
    return fig


def empty_fig(msg: str = "Select at least one airport") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        plot_bgcolor=CARD, paper_bgcolor=CARD, height=300,
        xaxis={"visible": False}, yaxis={"visible": False},
        annotations=[{"text": msg, "showarrow": False,
                      "font": {"size": 14, "color": "#CBD5E1", "family": FONT},
                      "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5}],
    )
    return fig


def mini_bar(value: float, max_val: float, accent: str) -> html.Div:
    pct = min(100.0, value / max_val * 100) if max_val else 0
    return html.Div(
        html.Div(style={
            "width": f"{pct:.1f}%", "height": "100%",
            "background": f"linear-gradient(90deg, {accent}70, {accent})",
            "borderRadius": "2px",
        }),
        style={"background": LIGHT, "borderRadius": "2px",
               "width": "72px", "height": "5px", "marginTop": "5px"},
    )


def filter_bar(dropdown_id, btn_all_id, btn_clear_id, airports, default=5):
    return html.Div([
        html.Div([
            html.Label("Filter Airports", style={
                "fontWeight": "700", "fontSize": "11px", "color": MUTED,
                "textTransform": "uppercase", "letterSpacing": "0.7px",
                "display": "block", "marginBottom": "8px",
            }),
            dcc.Dropdown(
                id=dropdown_id,
                options=[{"label": a, "value": a} for a in airports],
                value=airports[:default],
                multi=True,
                placeholder="Choose airports for comparison…",
                style={"fontSize": "13px"},
            ),
        ], style={"flex": "1"}),
        html.Div([
            html.Button("Select All", id=btn_all_id, n_clicks=0,
                        style={**BTN, "background": NAVY, "color": "#fff", "marginRight": "8px"}),
            html.Button("Clear", id=btn_clear_id, n_clicks=0,
                        style={**BTN, "background": LIGHT, "color": MUTED}),
        ], style={"display": "flex", "alignItems": "flex-end"}),
    ], style={
        "display": "flex", "gap": "20px", "alignItems": "flex-end",
        "background": CARD, "borderRadius": "14px",
        "padding": "18px 22px", "boxShadow": SHADOW,
        "marginBottom": "18px",
    })


def section_card(*children, title, subtitle=""):
    return html.Div([
        html.Div([
            html.H3(title, style={
                "margin": 0, "fontSize": "15px", "fontWeight": "700",
                "color": DARK, "letterSpacing": "-0.3px",
            }),
            html.P(subtitle, style={"margin": "4px 0 0", "fontSize": "11px", "color": MUTED}),
        ], style={"marginBottom": "16px"}),
        *children,
    ], style={"background": CARD, "borderRadius": "14px",
              "padding": "22px 24px", "boxShadow": SHADOW})


# ── Revenue tab charts & table ────────────────────────────────────────────────

def rev_scatter(df: pd.DataFrame) -> go.Figure:
    colors    = [COLOR_MAP.get(a, PALETTE[0]) for a in df["airport_name"]]
    show_text = len(df) <= 10
    fig = go.Figure(go.Scatter(
        x=df["total_bookings"], y=df["total_revenue"],
        mode="markers+text" if show_text else "markers",
        marker=dict(
            size=[max(14, r / 60) for r in df["avg_revenue_per_booking"]],
            color=colors, opacity=0.85, line=dict(width=2, color="#fff"),
        ),
        text=df["airport_name"].str.split().str[0] if show_text else None,
        textposition="top center", textfont={"size": 9, "color": MUTED},
        customdata=df[["airport_name", "avg_revenue_per_booking"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Bookings: %{x:,.0f}<br>Revenue: $%{y:,.2f}<br>"
            "Avg Rev/Booking: $%{customdata[1]:,.2f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title={"text": "Revenue vs Bookings  ·  bubble size = Avg Rev/Booking",
               "font": {"size": 13, "color": DARK}, "x": 0.01, "y": 0.98},
        xaxis=dict(title=dict(text="Total Bookings", font={"size": 11, "color": MUTED}),
                   showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickfont={"size": 10}),
        yaxis=dict(title=dict(text="Total Revenue ($)", font={"size": 11, "color": MUTED}),
                   showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickfont={"size": 10}),
        margin={"l": 52, "r": 24, "t": 44, "b": 40},
        height=max(280, len(df) * 44 + 80), showlegend=False, **CHART_BASE,
    )
    return fig


def rev_table(df: pd.DataFrame) -> html.Table:
    max_b = df["total_bookings"].max() or 1
    max_r = df["total_revenue"].max() or 1
    max_a = df["avg_revenue_per_booking"].max() or 1

    th = {"padding": "11px 14px", "background": DARK, "color": "#fff",
          "fontWeight": "600", "fontSize": "11px", "letterSpacing": "0.5px",
          "textTransform": "uppercase", "whiteSpace": "nowrap"}
    hdr = html.Thead(html.Tr([
        html.Th("Airport",               style={**th, "textAlign": "left"}),
        html.Th("City",                  style={**th, "textAlign": "left"}),
        html.Th("Country",               style={**th, "textAlign": "left"}),
        html.Th("Bookings",              style={**th, "textAlign": "right"}),
        html.Th("Revenue ($)",           style={**th, "textAlign": "right"}),
        html.Th("Avg Rev / Booking ($)", style={**th, "textAlign": "right"}),
    ]))
    td = lambda extra={}: {"padding": "9px 14px", "fontSize": "13px",
                           "color": DARK, "borderBottom": f"1px solid {BORDER}", **extra}
    rows = []
    for i, row in enumerate(df.itertuples()):
        clr = COLOR_MAP.get(row.airport_name, PALETTE[0])
        bg  = CARD if i % 2 == 0 else "#F8FAFC"
        rows.append(html.Tr([
            html.Td([
                html.Span(style={"display":"inline-block","width":"9px","height":"9px",
                                 "borderRadius":"50%","background":clr,
                                 "marginRight":"8px","verticalAlign":"middle"}),
                row.airport_name,
            ], style=td({"fontWeight":"500"})),
            html.Td(row.city,    style=td()),
            html.Td(row.country, style=td()),
            html.Td([html.Div(f"{int(row.total_bookings):,}",
                              style={"textAlign":"right","fontWeight":"600"}),
                     html.Div(mini_bar(row.total_bookings, max_b, "#3B82F6"),
                              style={"display":"flex","justifyContent":"flex-end"})], style=td()),
            html.Td([html.Div(f"${row.total_revenue:,.2f}",
                              style={"textAlign":"right","fontWeight":"600"}),
                     html.Div(mini_bar(row.total_revenue, max_r, "#10B981"),
                              style={"display":"flex","justifyContent":"flex-end"})], style=td()),
            html.Td([html.Div(f"${row.avg_revenue_per_booking:,.2f}",
                              style={"textAlign":"right","fontWeight":"600"}),
                     html.Div(mini_bar(row.avg_revenue_per_booking, max_a, "#F59E0B"),
                              style={"display":"flex","justifyContent":"flex-end"})], style=td()),
        ], style={"background": bg}))

    return html.Table([hdr, html.Tbody(rows)],
                      style={"width":"100%","borderCollapse":"collapse",
                             "borderRadius":"10px","overflow":"hidden"})


# ── Performance tab charts & table ────────────────────────────────────────────

def perf_booking_range(df: pd.DataFrame) -> go.Figure:
    """Grouped bar: Min / Avg / Max booking value — shows pricing breadth per airport."""
    s = df.sort_values("avg_booking_value")
    fig = go.Figure([
        go.Bar(name="Min Booking", x=s["airport_name"], y=s["min_booking_value"],
               marker=dict(color="#94A3B8", line=dict(width=0)),
               hovertemplate="<b>%{x}</b><br>Min: $%{y:,.2f}<extra></extra>"),
        go.Bar(name="Avg Booking", x=s["airport_name"], y=s["avg_booking_value"],
               marker=dict(color=NAVY,     line=dict(width=0)),
               hovertemplate="<b>%{x}</b><br>Avg: $%{y:,.2f}<extra></extra>"),
        go.Bar(name="Max Booking", x=s["airport_name"], y=s["max_booking_value"],
               marker=dict(color="#6366F1", line=dict(width=0)),
               hovertemplate="<b>%{x}</b><br>Max: $%{y:,.2f}<extra></extra>"),
    ])
    fig.update_layout(
        barmode="group",
        title={"text": "Booking Value Range  ·  Min / Avg / Max",
               "font": {"size": 13, "color": DARK}, "x": 0.01, "y": 0.98},
        xaxis=dict(showgrid=False, tickangle=-35, tickfont={"size": 9}),
        yaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False,
                   tickprefix="$", tickfont={"size": 10}),
        legend=dict(orientation="h", x=0, y=-0.30, font={"size": 11, "family": FONT}),
        margin={"l": 16, "r": 16, "t": 44, "b": 90},
        height=max(320, len(df) * 30 + 130),
        showlegend=True,
        **CHART_BASE,
    )
    return fig


def perf_scatter(df: pd.DataFrame) -> go.Figure:
    """Scatter: Flights vs Revenue — operational scale vs financial outcome."""
    colors    = [COLOR_MAP.get(a, PALETTE[0]) for a in df["airport_name"]]
    show_text = len(df) <= 10
    fig = go.Figure(go.Scatter(
        x=df["total_flights"], y=df["total_revenue"],
        mode="markers+text" if show_text else "markers",
        marker=dict(
            size=[max(12, p * 1.8) for p in df["unique_passengers"]],
            color=colors, opacity=0.85, line=dict(width=2, color="#fff"),
        ),
        text=df["airport_name"].str.split().str[0] if show_text else None,
        textposition="top center", textfont={"size": 9, "color": MUTED},
        customdata=df[["airport_name", "unique_passengers", "revenue_per_pax"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Flights: %{x:,.0f}<br>Revenue: $%{y:,.2f}<br>"
            "Passengers: %{customdata[1]:,.0f}<br>"
            "Rev / Passenger: $%{customdata[2]:,.2f}<extra></extra>"
        ),
    ))
    fig.update_layout(
        title={"text": "Operational Scale  ·  Flights vs Revenue  ·  bubble size = Passengers",
               "font": {"size": 13, "color": DARK}, "x": 0.01, "y": 0.98},
        xaxis=dict(title=dict(text="Total Flights", font={"size": 11, "color": MUTED}),
                   showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickfont={"size": 10}),
        yaxis=dict(title=dict(text="Total Revenue ($)", font={"size": 11, "color": MUTED}),
                   showgrid=True, gridcolor="#F1F5F9", zeroline=False, tickfont={"size": 10}),
        margin={"l": 52, "r": 24, "t": 44, "b": 40},
        height=max(280, len(df) * 44 + 80), showlegend=False, **CHART_BASE,
    )
    return fig


def perf_table(df: pd.DataFrame) -> html.Table:
    max_f   = df["total_flights"].max() or 1
    max_p   = df["unique_passengers"].max() or 1
    max_pf  = df["pax_per_flight"].max() or 1
    max_avg = df["avg_booking_value"].max() or 1
    max_rpp = df["revenue_per_pax"].max() or 1

    th = {"padding": "11px 14px", "background": DARK, "color": "#fff",
          "fontWeight": "600", "fontSize": "11px", "letterSpacing": "0.5px",
          "textTransform": "uppercase", "whiteSpace": "nowrap"}
    hdr = html.Thead(html.Tr([
        html.Th("Airport",             style={**th, "textAlign": "left"}),
        html.Th("City",                style={**th, "textAlign": "left"}),
        html.Th("Flights",             style={**th, "textAlign": "right"}),
        html.Th("Passengers",          style={**th, "textAlign": "right"}),
        html.Th("Pax / Flight",        style={**th, "textAlign": "right"}),
        html.Th("Avg Booking ($)",     style={**th, "textAlign": "right"}),
        html.Th("Max Booking ($)",     style={**th, "textAlign": "right"}),
        html.Th("Rev / Passenger ($)", style={**th, "textAlign": "right"}),
    ]))
    td = lambda extra={}: {"padding": "9px 14px", "fontSize": "13px",
                           "color": DARK, "borderBottom": f"1px solid {BORDER}", **extra}
    rows = []
    for i, row in enumerate(df.itertuples()):
        clr = COLOR_MAP.get(row.airport_name, PALETTE[0])
        bg  = CARD if i % 2 == 0 else "#F8FAFC"

        def metric_cell(val_str, bar_val, bar_max, bar_color):
            return html.Td([
                html.Div(val_str, style={"textAlign": "right", "fontWeight": "600"}),
                html.Div(mini_bar(bar_val, bar_max, bar_color),
                         style={"display": "flex", "justifyContent": "flex-end"}),
            ], style=td())

        rows.append(html.Tr([
            html.Td([
                html.Span(style={"display":"inline-block","width":"9px","height":"9px",
                                 "borderRadius":"50%","background":clr,
                                 "marginRight":"8px","verticalAlign":"middle"}),
                row.airport_name,
            ], style=td({"fontWeight":"500"})),
            html.Td(row.city, style=td()),
            metric_cell(f"{int(row.total_flights):,}",      row.total_flights,      max_f,   "#3B82F6"),
            metric_cell(f"{int(row.unique_passengers):,}",  row.unique_passengers,  max_p,   "#8B5CF6"),
            metric_cell(f"{row.pax_per_flight:.1f}",        row.pax_per_flight,     max_pf,  "#14B8A6"),
            metric_cell(f"${row.avg_booking_value:,.2f}",   row.avg_booking_value,  max_avg, "#F59E0B"),
            html.Td(f"${row.max_booking_value:,.2f}",
                    style=td({"textAlign":"right","fontWeight":"600"})),
            metric_cell(f"${row.revenue_per_pax:,.2f}",     row.revenue_per_pax,    max_rpp, "#10B981"),
        ], style={"background": bg}))

    return html.Table([hdr, html.Tbody(rows)],
                      style={"width":"100%","borderCollapse":"collapse",
                             "borderRadius":"10px","overflow":"hidden"})


# ── Dash app ──────────────────────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    title="Airport Analytics Dashboard",
    external_stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
    ],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

# ── Tab content ───────────────────────────────────────────────────────────────

revenue_content = html.Div([
    filter_bar("rev-airport-selector", "rev-btn-all", "rev-btn-clear", AIRPORTS),
    html.Div(id="rev-kpi-row", style={
        "display":"flex","gap":"14px","marginBottom":"18px","flexWrap":"wrap"}),
    html.Div([
        html.Div(dcc.Graph(id="rev-chart-bookings",   config={"displayModeBar":False}), style=CARD_WRAP),
        html.Div(dcc.Graph(id="rev-chart-revenue",    config={"displayModeBar":False}), style=CARD_WRAP),
    ], style={"display":"flex","gap":"16px","marginBottom":"16px","flexWrap":"wrap"}),
    html.Div([
        html.Div(dcc.Graph(id="rev-chart-avg-revenue", config={"displayModeBar":False}), style=CARD_WRAP),
        html.Div(dcc.Graph(id="rev-chart-scatter",     config={"displayModeBar":False}), style=CARD_WRAP),
    ], style={"display":"flex","gap":"16px","marginBottom":"18px","flexWrap":"wrap"}),
    section_card(
        html.Div(id="rev-detail-table"),
        title="Detailed Comparison",
        subtitle="Sorted by revenue (highest first) · bars show relative rank",
    ),
], style={"padding": "20px 0 0"})


perf_content = html.Div([
    filter_bar("perf-airport-selector", "perf-btn-all", "perf-btn-clear", AIRPORTS_PERF),
    html.Div(id="perf-kpi-row", style={
        "display":"flex","gap":"14px","marginBottom":"18px","flexWrap":"wrap"}),

    # Row 1: Revenue per Passenger | Passenger Load Index
    html.Div([
        html.Div(dcc.Graph(id="perf-chart-rev-per-pax",    config={"displayModeBar":False}), style=CARD_WRAP),
        html.Div(dcc.Graph(id="perf-chart-pax-per-flight", config={"displayModeBar":False}), style=CARD_WRAP),
    ], style={"display":"flex","gap":"16px","marginBottom":"16px","flexWrap":"wrap"}),

    # Row 2: Booking Value Range | Operational Scale Scatter
    html.Div([
        html.Div(dcc.Graph(id="perf-chart-booking-range", config={"displayModeBar":False}), style=CARD_WRAP),
        html.Div(dcc.Graph(id="perf-chart-scatter",       config={"displayModeBar":False}), style=CARD_WRAP),
    ], style={"display":"flex","gap":"16px","marginBottom":"18px","flexWrap":"wrap"}),

    section_card(
        html.Div(id="perf-detail-table"),
        title="Airport Performance Details",
        subtitle="Sorted by revenue (highest first) · bars show relative rank within selection",
    ),
], style={"padding": "20px 0 0"})

# ── App layout ────────────────────────────────────────────────────────────────

app.layout = html.Div([

    # Header
    html.Div([
        html.Div([
            html.Div([
                html.Div("✈", style={
                    "fontSize": "26px", "marginRight": "14px",
                    "background": "rgba(255,255,255,0.12)", "borderRadius": "10px",
                    "width": "46px", "height": "46px", "flexShrink": "0",
                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                }),
                html.Div([
                    html.H1("Airport Analytics Dashboard", style={
                        "margin": 0, "color": "#fff",
                        "fontSize": "20px", "fontWeight": "800", "letterSpacing": "-0.4px",
                    }),
                    html.P(
                        "Revenue summary & operational performance across global airports",
                        style={"margin": "3px 0 0", "color": "rgba(255,255,255,0.5)", "fontSize": "11px"},
                    ),
                ]),
            ], style={"display": "flex", "alignItems": "center"}),
            html.Div([
                html.Div(str(len(AIRPORTS)), style={
                    "fontSize": "32px", "fontWeight": "800", "color": "#fff",
                    "lineHeight": "1", "textAlign": "right",
                }),
                html.Div("airports tracked", style={
                    "color": "rgba(255,255,255,0.5)", "fontSize": "11px", "textAlign": "right",
                }),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                  "maxWidth":"1400px","margin":"0 auto"}),
    ], style={
        "background": f"linear-gradient(135deg, {DARK} 0%, {NAVY} 100%)",
        "padding": "18px 28px 20px",
    }),

    # Tab bar + content
    html.Div([
        dcc.Tabs(
            id="main-tabs",
            value="tab-revenue",
            colors={"border": BORDER, "primary": NAVY, "background": CARD},
            style={"borderBottom": f"1px solid {BORDER}", "marginBottom": "0"},
            children=[
                dcc.Tab(label="Airport Revenue",     value="tab-revenue",
                        style=TAB_STYLE, selected_style=SEL_TAB_STYLE,
                        children=revenue_content),
                dcc.Tab(label="Airport Performance", value="tab-performance",
                        style=TAB_STYLE, selected_style=SEL_TAB_STYLE,
                        children=perf_content),
            ],
        ),
    ], style={
        "background": CARD, "boxShadow": SHADOW,
        "maxWidth": "1400px", "margin": "0 auto", "padding": "0 28px 44px",
    }),

], style={"fontFamily": FONT, "background": LIGHT, "minHeight": "100vh"})

# ── Callbacks — Revenue tab ───────────────────────────────────────────────────

@app.callback(
    Output("rev-airport-selector", "value"),
    Input("rev-btn-all", "n_clicks"),
    Input("rev-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def rev_quick_select(*_):
    return AIRPORTS if ctx.triggered_id == "rev-btn-all" else []


@app.callback(
    Output("rev-kpi-row",         "children"),
    Output("rev-chart-bookings",  "figure"),
    Output("rev-chart-revenue",   "figure"),
    Output("rev-chart-avg-revenue","figure"),
    Output("rev-chart-scatter",   "figure"),
    Output("rev-detail-table",    "children"),
    Input("rev-airport-selector", "value"),
)
def update_revenue(selected):
    if not selected:
        ef = empty_fig()
        return ([], ef, ef, ef, ef,
                html.P("No airports selected.", style={"color": MUTED, "padding": "16px 0"}))

    filt = (DF[DF["airport_name"].isin(selected)]
            .sort_values("total_revenue", ascending=False).reset_index(drop=True))

    kpis = [
        kpi_card("✈", "Airports",      str(len(filt)),                                     NAVY,     f"of {len(AIRPORTS)} total"),
        kpi_card("#", "Total Bookings", f"{int(filt['total_bookings'].sum()):,}",            "#3B82F6"),
        kpi_card("$", "Total Revenue",  f"${filt['total_revenue'].sum():,.0f}",              "#10B981"),
        kpi_card("~", "Avg Rev / Bkg",  f"${filt['avg_revenue_per_booking'].mean():,.2f}",   "#F59E0B"),
    ]
    return (
        kpis,
        h_bar(filt, "total_bookings",         "Total Bookings"),
        h_bar(filt, "total_revenue",           "Total Revenue",      prefix="$"),
        h_bar(filt, "avg_revenue_per_booking", "Avg Revenue / Booking", prefix="$"),
        rev_scatter(filt),
        rev_table(filt),
    )


# ── Callbacks — Performance tab ───────────────────────────────────────────────

@app.callback(
    Output("perf-airport-selector", "value"),
    Input("perf-btn-all", "n_clicks"),
    Input("perf-btn-clear", "n_clicks"),
    prevent_initial_call=True,
)
def perf_quick_select(*_):
    return AIRPORTS_PERF if ctx.triggered_id == "perf-btn-all" else []


@app.callback(
    Output("perf-kpi-row",              "children"),
    Output("perf-chart-rev-per-pax",    "figure"),
    Output("perf-chart-pax-per-flight", "figure"),
    Output("perf-chart-booking-range",  "figure"),
    Output("perf-chart-scatter",        "figure"),
    Output("perf-detail-table",         "children"),
    Input("perf-airport-selector",      "value"),
)
def update_performance(selected):
    if not selected:
        ef = empty_fig()
        return ([], ef, ef, ef, ef,
                html.P("No airports selected.", style={"color": MUTED, "padding": "16px 0"}))

    filt = (DF_PERF[DF_PERF["airport_name"].isin(selected)]
            .sort_values("total_revenue", ascending=False).reset_index(drop=True))

    total_rev = filt["total_revenue"].sum()
    total_pax = filt["unique_passengers"].sum()
    total_bkg = filt["total_bookings"].sum()

    kpis = [
        kpi_card("✈", "Airports",         str(len(filt)),                              NAVY,     f"of {len(AIRPORTS_PERF)} total"),
        kpi_card("#", "Total Flights",     f"{int(filt['total_flights'].sum()):,}",     "#3B82F6"),
        kpi_card("+", "Unique Passengers", f"{int(total_pax):,}",                       "#8B5CF6"),
        kpi_card("$", "Rev / Passenger",   f"${total_rev / total_pax:,.2f}" if total_pax else "—", "#10B981"),
        kpi_card("~", "Avg Booking Value", f"${total_rev / total_bkg:,.2f}" if total_bkg else "—", "#F59E0B"),
    ]
    return (
        kpis,
        h_bar(filt, "revenue_per_pax",  "Revenue per Passenger",   prefix="$"),
        h_bar(filt, "pax_per_flight",   "Passenger Load Index  ·  Pax per Flight"),
        perf_booking_range(filt),
        perf_scatter(filt),
        perf_table(filt),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
