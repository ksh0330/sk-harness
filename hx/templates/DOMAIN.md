# Semiconductor task reference

The actual contest scope is unknown. These are candidate domains, not predictions. Read only the relevant section and let the task's definitions prevail.

## Terms

| Term | Working meaning |
|---|---|
| Fab / front end | Wafer fabrication with repeated lithography, etch, deposition, diffusion, implantation, CMP, cleaning and metrology steps; routes may revisit equipment families |
| Back end / HBM | Packaging and testing; HBM stacks dies using TSV interconnects |
| Lot / wafer / die | A lot is a moving group of wafers, commonly up to 25 in a FOUP; a wafer contains many dies. Preserve the lot → wafer → die key hierarchy |
| EQP / chamber / recipe | Equipment, its process chamber, and process settings. Different chambers or recipes need not share a population |
| MES | Manufacturing execution system, including track-in/out, WAIT/RUN/HOLD and equipment states |
| FDC | Fault detection and classification using sensor traces or step/run summaries |
| SPC | Statistical process control. Control limits and specification limits are distinct; verify the appropriate chart and run rules |
| Cp / Cpk | Cp = (USL−LSL)/(6σ); Cpk = min(USL−μ, μ−LSL)/(3σ), subject to applicable statistical assumptions |
| Metrology / VM | Physical measurements such as thickness, CD or overlay; virtual metrology predicts these from process signals |
| APC / R2R | Process control that adjusts subsequent run settings using feedback |
| WAT / PCM / ET | Electrical measurement of test structures after fabrication |
| EDS / probe | Die-level wafer testing, often represented by bin codes and wafer maps |
| Yield | Good dies divided by the applicable tested population; confirm denominators and aggregation level |
| Wafer map | Spatial patterns such as center, ring, edge, scratch or random defects; a clue, not proof of cause |
| PM / BM | Preventive / breakdown maintenance. MTBF and MTTR describe failure and repair intervals |
| OEE | Availability × performance × quality |
| WIP / TAT | Work in progress / turnaround or cycle time |
| Q-time | Maximum allowed interval between specified process steps |
| Dispatching | Choosing the next eligible lot, e.g. FIFO, EDD, SPT or critical ratio |
| Hold / rework / scrap | Suspended work / repeat processing / discarded material |
| Excursion / commonality | Abnormal process event / investigation of shared routes or exposures |

## Shared checks

- Verify join keys, parent references, whitespace/case conventions and row counts before and after joins. Typical keys include lot, wafer, step, equipment, chamber and timestamp.
- Check time order, timezone, mixed formats, default dates and missing intervals. Track-in must precede track-out under the task's rules.
- Confirm units, 0–1 versus 0–100 scales, sentinel values, missing versus zero, and equipment/recipe-specific ranges.
- Measure a simple baseline before improvements. Use time/group splits to prevent future information or the same lot/wafer leaking across train and evaluation.
- Exclude post-outcome labels or action codes from predictors. Report sample sizes and uncertainty; association is not causation.
- Tie each finding to equipment/lot/time, observed values, criteria and proposed action. Use existing tools (`hx doctor`), not assumed package/network availability.

## Candidate approaches

| Task | Baseline | Verification and pitfalls |
|---|---|---|
| Process anomalies | Grouped median/MAD or EWMA; consider other methods only with evidence | Precision/recall and PR-AUC with labels; injected anomalies and false alarms otherwise. Do not mix populations or mistake maintenance/recipe shifts for defects |
| Yield analysis | Grouped yield summaries and shared-route analysis | Sample counts, product/time confounding, consistent die/wafer weighting |
| Failure prediction / PM | Trends and threshold rules compared with periodic maintenance | Time split, lead time and false alarms; avoid post-failure leakage and ignore neither maintenance resets nor rare-event scarcity |
| Lot scheduling / allocation | EDD/SPT/CR greedy, then local search or an available solver | Independently validate eligibility, no overlap, exact coverage, time bounds, downtime, setup and Q-time. Compare objective with baseline/bounds and fix seeds |
| Logs / events | Normalize equipment, codes and timestamps; aggregate transitions | Verify known events and count conservation; handle duplicate/out-of-order events and distinguish missing logs from no events |
| Reconciliation / automation | Key-based missing/duplicate/value/timing differences | Explicit rules and violation lists; preserve original inputs, handle merged Excel headers and representation differences |
| Decision dashboard | Reproducible metric definitions and aggregates | Hand-check examples and filter totals; a polished display is not numeric evidence |

## Deliverable shape

Follow the specified format. If unspecified, a reproducible command, result files and concise README are a practical baseline; add a UI when exploration or interaction adds value. `hx new app` is an offline standard-library scaffold, not a finished product or persistent database. Avoid CDN dependencies; use local assets or available plotting tools.
