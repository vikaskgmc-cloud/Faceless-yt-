"""Built-in demo storyboard: exercises every visual type with ILLUSTRATIVE data
(nothing here is a real company or real number)."""

ILL = {"illustrative": True}


def V(t, d=None, sfx=None):
    v = {"type": t, "data": {**(d or {}), **ILL}}
    if sfx:
        v["sfx"] = sfx
    return v


# (act, pace, narration, [visuals])
DEMO = [
    ("cold_open", "slow",
     "This is a demonstration of every scene type, using made up numbers, not a real company.",
     [V("title", {"kicker": "PRODUCTION DEMO", "text": "How a floating-rate loan *breaks* a deal"})]),
    ("cold_open", "fast",
     "In seventy two hours, one hundred million dollars of investor equity was gone.",
     [V("stat", {"prefix": "$", "value": 100, "suffix": "M", "label": "of investor equity wiped out",
                 "chip": "ILLUSTRATIVE"}, "sub_drop"),
      V("text", {"text": "No *warning*. No second chance."})]),
    ("rise", "normal",
     "Picture the scene: a neighbourhood of apartment blocks, where every unit was financed on the same assumptions.",
     [V("clip", {"file": "demo_clip.mp4", "caption": "Generated demo footage", "own": False})]),
    ("rise", "normal",
     "At first, the projections looked great, and investors kept piling in, year after year.",
     [V("line", {"title": "Projected annual return", "unit": "%",
                 "points": [{"x": "2019", "y": 6}, {"x": "2020", "y": 9}, {"x": "2021", "y": 14},
                            {"x": "2022", "y": 19}],
                 "annotations": [{"index": 3, "text": "Pitch peak"}]}),
      V("units", {"title": "The portfolio", "total": 3200, "affected": 0, "label": "units acquired",
                  "sub": "across four properties"})]),
    ("flaw", "normal",
     "Here is how the money moved, and where the weak link sat in the chain.",
     [V("flow", {"title": "Where the money went", "highlight": 3,
                 "nodes": ["Retail investors", "Syndicator", "Apartment property", "Floating-rate lender"],
                 "labels": ["equity", "purchase", "bridge loan"]}),
      V("layer", {"number": 1, "title": "The floating rate",
                  "text": "When interest rates rise, the loan payment rises with them."})]),
    ("flaw", "normal",
     "Rent stayed flat, while the loan payment more than doubled in just two years.",
     [V("bars", {"title": "Monthly rent vs debt payment", "unit": "M", "prefix": "$",
                 "bars": [{"label": "Rent", "value": 4.2, "color": "grey"},
                          {"label": "Debt, before", "value": 3.8, "color": "grey"},
                          {"label": "Debt, after", "value": 9.1, "color": "red"}],
                 "line": {"value": 4.2, "label": "Rent covers up to here"}}),
      V("gauge", {"title": "Debt service coverage", "value": 0.69, "threshold": 1.0, "min": 0, "max": 2,
                  "label": "Below 1.0, rent cannot cover the loan payment", "threshold_label": "1.00 = break-even"})]),
    ("collapse", "fast",
     "Payments jumped, reserves drained, and the lender moved to take the properties.",
     [V("timeline", {"title": "How it unfolded",
                     "events": [{"when": "Month 0", "what": "Rates start rising"},
                                {"when": "Month 6", "what": "Payments jump"},
                                {"when": "Month 12", "what": "Reserves run out"},
                                {"when": "Month 14", "what": "Lender acts"}]}, "tick"),
      V("units", {"title": "Properties lost", "total": 3200, "affected": 3200, "label": "units foreclosed",
                  "sub": "in a single month"}, "beep"),
      V("text", {"text": "Because income stalled, *reserves drained*"})]),
    ("lesson", "normal",
     "The key lesson is simple. The lender gets paid first, and investors take the loss first.",
     [V("stack", {"title": "The capital stack", "value_drop": 72,
                  "layers": [{"label": "Investor equity", "share": 25, "note": "Paid last, loses first"},
                             {"label": "Mezzanine debt", "share": 10, "note": "Paid after the senior lender"},
                             {"label": "Senior loan", "share": 65, "note": "Paid first"}]}),
      V("quote", {"label": "According to a court filing", "date": "ILLUSTRATIVE",
                  "quote": "The borrower failed to make the payment due under the loan agreement.",
                  "highlight": "failed to make the payment", "source": "Illustrative document"})]),
    ("lesson", "normal",
     "Before you invest, check what happens to the debt payment if rates move against you.",
     [V("table", {"title": "What happened vs the rule", "left_header": "What they did", "right_header": "The rule",
                  "rows": [["Used floating-rate debt", "Match debt to the income it must be paid from"],
                           ["Skipped a cash cushion", "Hold reserves for rate shocks"],
                           ["Assumed rents only rise", "Stress-test the plan with flat rents"]]})]),
    ("outro", "slow",
     "It was never a failure of intelligence. It was a failure of incentives. Click the video on screen now.",
     [V("text", {"text": "A failure of *incentives*"}), V("title", {"kicker": "UP NEXT", "text": "Click the video on screen now"})]),
]
