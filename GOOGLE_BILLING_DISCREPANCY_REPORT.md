# Google Cloud Billing Discrepancy Report

**Date:** January 25, 2026  
**Service:** Gemini API  
**Model:** gemini-2.5-flash-native-audio-preview-12-2025  
**API Type:** BidiGenerateContent (Live API / Bidirectional Streaming)

---

## Executive Summary

A billing analysis reveals that actual charges for the Gemini 2.5 Flash Native Audio API are approximately **35% higher** than the rates published in Google's official pricing documentation.

---

## Billing Comparison

| Token Type    | Tokens Used | Amount Billed | Actual Rate/1M | Official Rate/1M | Variance |
|---------------|-------------|---------------|----------------|------------------|----------|
| Audio output  | 92,231      | $1.51         | **$16.37**     | $12.00           | **+36%** |
| Text input    | 1,130,042   | $0.77         | **$0.68**      | $0.50            | **+36%** |
| Audio input   | 17,821      | $0.07         | **$3.93**      | $3.00            | **+31%** |
| Text output   | 2,301       | $0.01         | **$4.35**      | $2.00            | **+117%*** |

\* *Text output variance appears inflated due to minimum charge rounding on small token counts*

**Total Billed:** $2.36  
**Expected (Official Rates):** $1.73  
**Overcharge:** $0.63 (+36%)

---

## SKU Details from Billing

| SKU Description | SKU ID | Usage | Cost |
|-----------------|--------|-------|------|
| BidiGenerateContent audio output token count for Gemini 2.5 Flash Native Audio | 6DDF-291A-5433 | 92,231 | $1.51 |
| BidiGenerateContent text input token count for Gemini 2.5 Flash Native Audio | 7B50-02E9-2A4D | 1,130,042 | $0.77 |
| BidiGenerateContent audio input token count for Gemini 2.5 Flash Native Audio | 25A5-7CA0-59C2 | 17,821 | $0.07 |
| BidiGenerateContent text output token count for Gemini 2.5 Flash Native Audio | 3DD9-488D-B378 | 2,301 | $0.01 |

---

## Official Pricing Reference

**Source:** https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-native-audio

### Gemini 2.5 Flash Native Audio (Live API) - Paid Tier

| Type | Official Rate (per 1M tokens) |
|------|-------------------------------|
| Input price - Text | $0.50 |
| Input price - Audio/Video | $3.00 |
| Output price - Text | $2.00 |
| Output price - Audio | $12.00 |

---

## Questions for Google Support

1. **Is there different pricing for BidiGenerateContent (Live API/bidirectional streaming) vs standard GenerateContent calls?**

2. **Does the preview model (`gemini-2.5-flash-native-audio-preview-12-2025`) have different rates than the documented stable version?**

3. **Why is there a consistent ~35% markup across all token types compared to published rates?**

4. **Can you provide the correct/current pricing for the SKUs listed above?**

---

## Impact Assessment

At current usage patterns, the pricing discrepancy results in:

- **Per-session impact:** ~36% higher costs than budgeted
- **At scale (10,000 calls/month):** Could represent significant unplanned expense
- **Planning impact:** Unable to accurately forecast costs using published documentation

---

## Requested Resolution

1. Clarification on actual vs. documented pricing
2. If pricing documentation is incorrect, request for update
3. If billing is incorrect, request for credit/adjustment
4. Published pricing for `BidiGenerateContent` SKUs specifically

---

## Contact Information

**Project:** Smart Shipping Bidirectional Voice Assistant  
**Environment:** Google Cloud Run (us-central1)  
**API Key Type:** Google AI Studio API Key  

---

*Report generated from billing data analysis - January 2026*
