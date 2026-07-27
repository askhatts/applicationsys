/* Графики дэшборда: данные приходят из /dashboard/data (JSON). */
(function () {
  "use strict";

  var COLORS = {
    blue: "#0f6cbd",
    red: "#d64545",
    palette: ["#0f6cbd", "#2e8b57", "#b07d12", "#7c3aed", "#d64545",
              "#0891b2", "#be185d", "#4d7c0f", "#9a3412", "#475569"],
  };

  function barWithOverdue(canvasId, series, horizontal) {
    var ctx = document.getElementById(canvasId);
    if (!ctx) return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: series.labels,
        datasets: [
          {
            label: "Просроченные",
            data: series.overdue,
            backgroundColor: COLORS.red,
            stack: "s",
          },
          {
            label: "Остальные",
            data: series.counts.map(function (c, i) { return c - series.overdue[i]; }),
            backgroundColor: COLORS.blue,
            stack: "s",
          },
        ],
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        responsive: true,
        scales: {
          x: { stacked: true, ticks: { precision: 0 } },
          y: { stacked: true, ticks: { precision: 0, autoSkip: false } },
        },
      },
    });
  }

  fetch(window.DASHBOARD_DATA_URL, { headers: { Accept: "application/json" } })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      barWithOverdue("chart-departments", data.by_department, true);
      barWithOverdue("chart-services", data.by_service, false);

      var cat = document.getElementById("chart-categories");
      if (cat) {
        new Chart(cat, {
          type: "doughnut",
          data: {
            labels: data.by_category.labels,
            datasets: [{ data: data.by_category.counts,
                         backgroundColor: COLORS.palette }],
          },
          options: { responsive: true },
        });
      }

      var days = document.getElementById("chart-days");
      if (days) {
        new Chart(days, {
          type: "line",
          data: {
            labels: data.by_day.labels,
            datasets: [{
              label: "Подано заявок",
              data: data.by_day.counts,
              borderColor: COLORS.blue,
              backgroundColor: "rgba(15,108,189,.15)",
              fill: true,
              tension: 0.25,
            }],
          },
          options: {
            responsive: true,
            scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
          },
        });
      }
    })
    .catch(function (err) { console.error("Не удалось загрузить данные графиков", err); });
})();
