# Analytical Nebula Dashboard Visual Refresh

Date: 2026-05-04

## Goal

Apply a subtle analytical-nebula visual refresh to the whole Streamlit dashboard. The refresh must improve atmosphere and visual hierarchy without reducing readability or changing any pipeline, merge, filtering, chart, or calculation logic.

## Scope

Applies to the full dashboard UI:
- project/sidebar controls;
- dashboard navigation tabs;
- filter/settings panels;
- metric context blocks;
- percentile cards;
- chart containers;
- tables/data sections;
- status/progress messages.

Does not change:
- data processing;
- metric calculations;
- bin logic;
- route logic;
- project/run storage;
- dashboard interaction flow.

## Chosen Direction

Use the `Chart Safe` direction from the mockup:
- dark analytical base;
- nebula only at the right and lower edges;
- no bright decorative layer directly under charts, tables, or controls;
- soft translucent panels with thin blue-gray borders;
- rounded analytical cards with restrained colored accents;
- pill-style navigation tabs;
- consistent spacing between analytical sections.

## Visual Rules

Background:
- add a fixed, non-interactive decorative layer using CSS gradients;
- place nebula emphasis on the right/lower page edges;
- keep the central content area dark enough for charts and tables.

Panels:
- use dark translucent surfaces;
- use subtle borders and internal highlights;
- keep high contrast for text and numbers.

Cards:
- keep P25 green, P85 red, custom percentile amber;
- use left accent border plus soft tinted background;
- preserve the unified percentile-card layout already implemented.

Controls:
- apply the style globally, but avoid breaking Streamlit widgets;
- keep long selectbox values wrapping by words;
- avoid heavy animations.

Charts and tables:
- wrap in visually consistent dark containers where Streamlit allows CSS targeting;
- do not recolor Plotly data traces globally, because chart colors already carry analytical meaning.

## Implementation Notes

Implement as a CSS-only layer in `dashboard_css()` as much as possible. Prefer Streamlit-compatible CSS selectors and avoid broad selectors that can break widget behavior. If a selector is fragile, keep the effect conservative.

## Acceptance Criteria

- The visual refresh appears across the whole dashboard, not only analytical tabs.
- Charts, filters, and tables remain readable.
- Existing functionality and tests continue to pass.
- Long metric names in filters still wrap instead of being truncated.
- The background does not visually compete with chart data.
