import Plot from "react-plotly.js";

interface Props {
  spec: Record<string, unknown>;
}

export default function PlotlyChart({ spec }: Props) {
  const data = (spec.data || []) as Plotly.Data[];
  const layout = {
    ...(spec.layout as Partial<Plotly.Layout> || {}),
    autosize: true,
    margin: { t: 60, r: 20, b: 40, l: 50 },
  };

  return (
    <div style={{ width: "100%", minHeight: 350 }}>
      <Plot
        data={data}
        layout={layout}
        config={{
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
          displaylogo: false,
        }}
        style={{ width: "100%", height: "100%" }}
        useResizeHandler
      />
    </div>
  );
}
