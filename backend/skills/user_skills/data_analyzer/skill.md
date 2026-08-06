---
name: data-analyzer
description: Data analysis, visualization, insights generation, statistical analysis, and data-driven decision making
emoji: 📊
priority: 2
---

## Instructions

When user needs data analysis help, or says:
- "Data analyze koro"
- "Chart banao"
- "Insights dekhao"
- "Statistics calculate koro"  
- "Trend analysis koro"

Activate **Data Analyzer Mode**:

### 1. 📊 Quick Data Overview

```
📊 DATA QUICK ANALYSIS

**Dataset:** sales_data.csv (1,247 rows, 8 columns)

**🔍 FIRST LOOK:**
```
    date        product      sales   revenue  region
0   2026-01-01  Laptop      45      67,500   North
1   2026-01-01  Phone       32      25,600   South  
2   2026-01-01  Tablet      18      10,800   East
3   2026-01-02  Laptop      52      78,000   North
4   2026-01-02  Phone       41      32,800   West
```

**📈 SUMMARY STATISTICS:**
```
                Sales    Revenue     
count           1,247    1,247      
mean            38.4     35,420     
std             15.2     18,750     
min             5        2,400      
25%             27       22,100     
50% (median)    36       31,200     
75%             48       45,800     
max             89       124,600    
```

**✨ KEY INSIGHTS:**
- Peak sales day: March 15 (89 units)
- Best performing region: North (34% of total revenue)  
- Top product: Laptops (52% of revenue)
- Growth trend: +12% month-over-month
- Seasonal pattern: Higher sales in Q1 & Q4
```

### 2. 📈 Trend Analysis

```
📈 SALES TREND ANALYSIS

**Time Series: Daily Sales (Last 90 Days)**

```
Sales Volume Trend:
90 ┤           ╭─╮
80 ┤         ╭─╯ ╰─╮
70 ┤       ╭─╯     ╰─╮
60 ┤     ╭─╯         ╰─╮
50 ┤   ╭─╯             ╰─╮
40 ┼─╭─╯                 ╰──
30 ┤
   └─────────────────────────
   Jan   Feb   Mar   Apr   May
```

**📊 TREND COMPONENTS:**

**Overall Trend:** ↗️ Growing (+15.3%)
- Linear growth: +0.45 units/day
- R² = 0.847 (Strong correlation)

**Seasonality:** 📅 Weekly Pattern Detected
- Monday: Lowest (32 avg)
- Tuesday-Thursday: Peak (45-48 avg)  
- Friday: High (42 avg)
- Weekend: Moderate (38 avg)

**🔮 FORECAST (Next 30 Days):**
```
Expected Sales Range:
Week 1: 42-48 units/day
Week 2: 44-50 units/day  
Week 3: 46-52 units/day
Week 4: 48-54 units/day

Confidence Interval: 95%
Expected Growth: +8.2%
```

**⚠️ ANOMALIES DETECTED:**
- April 12: Sales dropped to 12 (Expected: 45)
- March 8: Sales spiked to 89 (Expected: 42)
- Possible causes: Holiday/promotion/system issues
```

### 3. 🎯 Customer Segmentation

```
🎯 CUSTOMER SEGMENTATION ANALYSIS

**RFM Analysis** (Recency, Frequency, Monetary)

**📊 CUSTOMER SEGMENTS:**

**💎 Champions (8.5% - 127 customers)**
- Recency: 1-15 days
- Frequency: 15+ orders
- Monetary: $5,000+
- Behavior: Frequent buyers, high spenders
- Action: VIP treatment, exclusive offers

**🌟 Loyal Customers (15.2% - 228 customers)** 
- Recency: 16-30 days
- Frequency: 8-14 orders
- Monetary: $2,000-$4,999
- Behavior: Regular buyers, good value
- Action: Loyalty programs, upselling

**💰 Big Spenders (12.7% - 190 customers)**
- Recency: 31-60 days  
- Frequency: 3-7 orders
- Monetary: $3,000+
- Behavior: High value, infrequent
- Action: Win-back campaigns

**🆕 New Customers (18.9% - 284 customers)**
- Recency: 1-30 days
- Frequency: 1-2 orders
- Monetary: $100-$500
- Behavior: Testing the waters
- Action: Onboarding, welcome offers

**😴 At Risk (22.4% - 335 customers)**
- Recency: 61-120 days
- Frequency: 5-10 orders  
- Monetary: $1,000+
- Behavior: Was loyal, now inactive
- Action: Re-engagement campaigns

**💔 Lost Customers (22.3% - 334 customers)**
- Recency: 120+ days
- Frequency: Any
- Monetary: Any
- Behavior: Churned
- Action: Win-back or write-off

**SEGMENT VISUALIZATION:**
```
         High Frequency
              │
Champions  │  Loyal
(💎 8.5%)  │  (🌟 15.2%)
───────────┼───────────
Big        │  New
Spenders   │  Customers  
(💰 12.7%) │  (🆕 18.9%)
              │
         Low Frequency
```

**💡 ACTIONABLE INSIGHTS:**
1. Focus on converting "New Customers" to "Loyal"
2. Urgent: Re-engage "At Risk" segment (22.4%!)
3. Opportunity: Increase frequency for "Big Spenders"
```

### 4. 📋 Statistical Testing

```
📋 STATISTICAL ANALYSIS

**HYPOTHESIS TEST: A/B Campaign Performance**

**Question:** Does the new email template increase click-through rates?

**Setup:**
- Control Group (A): Old template - 1,000 users
- Test Group (B): New template - 1,000 users
- Metric: Click-through rate (CTR)
- Significance Level: α = 0.05

**Results:**
```
Group    Users   Clicks   CTR     
A        1,000   87       8.7%    
B        1,000   124      12.4%   
```

**Statistical Test: Two-Proportion Z-Test**

```
H₀: CTR_A = CTR_B (No difference)
H₁: CTR_A ≠ CTR_B (There is a difference)

Sample proportions:
p̂₁ = 0.087 (Group A)
p̂₂ = 0.124 (Group B)

Pooled proportion:
p̂ = (87 + 124)/(1000 + 1000) = 0.1055

Standard error:
SE = √[p̂(1-p̂)(1/n₁ + 1/n₂)] = 0.0137

Z-score: (0.124 - 0.087)/0.0137 = 2.70
P-value: 0.0069
```

**📊 CONCLUSION:**
✅ **STATISTICALLY SIGNIFICANT** (p < 0.05)

- New template increases CTR by 3.7 percentage points
- 95% Confidence Interval: [1.0%, 6.4%]
- Effect Size: 42.5% relative improvement
- Statistical Power: 84.3%

**💰 BUSINESS IMPACT:**
- Expected lift: +42.5% more clicks
- Revenue impact: ~$15,000/month
- Recommendation: ✅ **Deploy new template**

**🔄 ADDITIONAL TESTS NEEDED:**
- Conversion rate impact
- Long-term engagement effects
- Segment-specific performance
```

### 5. 🧮 Correlation & Regression Analysis

```
🧮 CORRELATION ANALYSIS

**Sales Factors Analysis**

**📊 CORRELATION MATRIX:**
```
                Price  Marketing  Season  Weather  Sales
Price           1.00   -0.23      0.08    0.02    -0.67
Marketing      -0.23    1.00      0.15    -0.05    0.54
Season          0.08    0.15      1.00     0.78    0.31
Weather         0.02   -0.05      0.78     1.00    0.29
Sales          -0.67    0.54      0.31     0.29    1.00
```

**🔍 KEY CORRELATIONS:**

**Strong Correlations (|r| > 0.5):**
- Price ↔ Sales: r = -0.67 (Strong negative) 🔴
  → Higher prices = Lower sales (expected)
  
- Marketing ↔ Sales: r = 0.54 (Moderate positive) 🟢
  → More marketing spend = Higher sales

- Season ↔ Weather: r = 0.78 (Strong positive) 🟢
  → Expected correlation (winter = cold weather)

**📈 REGRESSION MODEL: Sales Prediction**

```
Multiple Linear Regression:
Sales = β₀ + β₁(Price) + β₂(Marketing) + β₃(Season) + β₄(Weather) + ε

Results:
Sales = 145.2 - 0.89(Price) + 0.34(Marketing) + 12.5(Season) + 0.18(Weather)

Coefficients:
β₁ = -0.89 (Price): $1 increase → 0.89 units decrease ⚠️
β₂ = 0.34 (Marketing): $1 marketing → 0.34 units increase ✅
β₃ = 12.5 (Season): Winter sales 12.5 units higher ✅
β₄ = 0.18 (Weather): Minimal impact

Model Performance:
R² = 0.743 (74.3% variance explained) ✅
Adjusted R² = 0.731
F-statistic: 68.4 (p < 0.001) ✅
```

**🎯 BUSINESS INSIGHTS:**
1. **Price Sensitivity:** Every $1 price increase costs 0.89 unit sales
2. **Marketing ROI:** $1 marketing spend = 0.34 extra sales
3. **Seasonal Effect:** Winter boost of 12.5 units (prepare inventory!)
4. **Weather:** Minimal direct impact (r = 0.29)

**💡 RECOMMENDATIONS:**
- Optimal price point: $85-95 (sweet spot analysis)
- Increase winter marketing budget by 25%
- Focus marketing on price-sensitive segments
```

### 6. 📊 Advanced Visualizations

```
📊 DATA VISUALIZATION DASHBOARD

**SALES PERFORMANCE DASHBOARD**

**📈 Revenue Heatmap by Region & Month:**
```
        Jan   Feb   Mar   Apr   May   Jun
North   🟩🟩🟩 🟨🟨🟨 🟩🟩🟩 🟨🟨🟨 🟩🟩🟩 🟨🟨🟨
South   🟨🟨🟨 🟩🟩🟩 🟨🟨🟨 🟩🟩🟩 🟨🟨🟨 🟩🟩🟩  
East    🟥🟥🟥 🟨🟨🟨 🟩🟩🟩 🟨🟨🟨 🟥🟥🟥 🟨🟨🟨
West    🟩🟩🟩 🟥🟥🟥 🟨🟨🟨 🟩🟩🟩 🟨🟨🟨 🟥🟥🟥

Legend: 🟩 High (>$50k)  🟨 Medium ($30-50k)  🟥 Low (<$30k)
```

**📊 Product Performance Bubble Chart:**
```
Revenue vs Units Sold (Bubble = Profit Margin)

$150k ┤                    ●(Laptop)
       ┤                ○
$100k  ┤            ○         
       ┤        ●(Phone)      ●(Monitor)
$50k   ┤    ○              
       ┤○(Tablet)        ○(Mouse)  
$0     └──────────────────────────────
       0    500   1000  1500  2000
               Units Sold
```

**📈 Time Series Decomposition:**
```
Original Sales:
80 ┤  ╭─╮    ╭─╮    ╭─╮
60 ┤╭─╯ ╰─╮╭─╯ ╰─╮╭─╯ ╰─╮
40 ┼╯     ╰╯     ╰╯     ╰

Trend Component:
50 ┤        ╭─────────────
40 ┤    ╭───╯
30 ┼────╯

Seasonal Component:  
10 ┤ ╭─╮    ╭─╮    ╭─╮
 0 ┼─╯ ╰────╯ ╰────╯ ╰
-10┤

Random Component:
 5 ┤  ╭─╮  ╭╮   ╭─╮
 0 ┼──╯ ╰──╯╰───╯ ╰──
-5 ┤
```

**🎯 Conversion Funnel:**
```
Website Visitors     10,000 (100%)
    ↓ (-87%)
Product Views         1,300 (13%)
    ↓ (-69%)  
Add to Cart             400 (3.1%)
    ↓ (-50%)
Checkout                200 (1.6%)  
    ↓ (-20%)
Purchase                160 (1.3%)

Biggest Drop: Visitors → Product Views (-87%)
Action Needed: Improve homepage engagement
```
```

### 7. 🔮 Predictive Analytics

```
🔮 PREDICTIVE ANALYTICS

**SALES FORECAST MODEL**

**Algorithm:** Prophet (Facebook's Time Series Forecasting)

**Historical Performance:**
- Training Period: Jan 2025 - Jul 2026 (18 months)
- Validation MAPE: 8.3% (Good accuracy) ✅
- Trend Component: +12% year-over-year growth
- Seasonality: Q4 peak, Q2 dip detected

**📈 30-Day Forecast:**
```
Date Range: Aug 5 - Sep 4, 2026

Daily Sales Forecast:
Week 1 (Aug 5-11):   42-48 units/day (Confidence: 85%)
Week 2 (Aug 12-18):  45-51 units/day (Confidence: 82%)  
Week 3 (Aug 19-25):  43-49 units/day (Confidence: 78%)
Week 4 (Aug 26-Sep 1): 46-52 units/day (Confidence: 75%)

Expected Events Impact:
- Aug 15 (Holiday): +25% sales spike
- Aug 22 (Competitor launch): -10% sales dip
- Aug 30 (Our promotion): +35% sales boost
```

**🎯 CUSTOMER CHURN PREDICTION**

**Model:** Gradient Boosting (XGBoost)
**Accuracy:** 89.3%
**Features Used:** 
- Days since last purchase
- Order frequency
- Average order value
- Customer support tickets
- Email engagement rate

**🚨 HIGH RISK CUSTOMERS (Next 30 Days):**
```
Customer ID   Churn Risk   Value    Action
CUS-12456     94%         $12,500  🚨 Immediate intervention
CUS-78901     87%         $8,400   ⚠️  Personal outreach  
CUS-34567     82%         $6,700   📞 Retention call
CUS-90123     78%         $4,200   📧 Targeted offer
CUS-45678     71%         $3,800   📨 Re-engagement email
```

**💰 REVENUE IMPACT:**
- At-risk revenue: $234,600 (18 customers)
- Expected churn without intervention: 67%
- Potential loss: $157,200
- Intervention cost: $12,000
- **ROI of retention campaign: 1,210%** 🎯

**🔄 RECOMMENDED ACTIONS:**
1. Personal call within 48 hours (94%+ risk)
2. Exclusive discount offer (80-90% risk)  
3. Product recommendation email (70-80% risk)
4. Monitor and re-score weekly
```

### 8. 🔍 Data Quality Assessment

```
🔍 DATA QUALITY REPORT

**Dataset:** customer_transactions.csv

**📊 OVERALL SCORE: 7.2/10** (Good quality)

**✅ QUALITY DIMENSIONS:**

**1. Completeness: 8.5/10**
```
Column              Missing    %Missing   Status
customer_id         0          0.0%      ✅ Perfect
transaction_date    0          0.0%      ✅ Perfect
amount             23          1.8%      ✅ Good
product_category    156        12.1%     ⚠️  Concerning
customer_email     45          3.5%      ✅ Acceptable
payment_method     0          0.0%      ✅ Perfect
```

**2. Accuracy: 7.8/10**
```
Issue                              Count    %Total   Impact
Invalid email formats              34       2.7%     Low
Negative transaction amounts       8        0.6%     High
Future transaction dates           12       0.9%     High  
Invalid product categories         67       5.2%     Medium
Duplicate customer records         23       1.8%     Medium
```

**3. Consistency: 6.9/10**
```
Inconsistency                      Examples              Count
Date formats                       "2026-01-01" vs      45
                                  "01/01/2026"
Currency formats                   "$100" vs "100.00"   78
Product names                      "iPhone" vs           156
                                  "Apple iPhone"
Country codes                      "US" vs "USA"        234
```

**4. Timeliness: 8.0/10**
```
Data Freshness:
- Latest record: 2026-08-04 (Today) ✅
- 95% of data: Within 30 days ✅
- Batch delays: 2 hours avg (Target: 1 hour) ⚠️
```

**🛠️ DATA CLEANING ACTIONS:**

**Immediate (Critical):**
1. Fix negative amounts (8 records) - Set to absolute value
2. Correct future dates (12 records) - Flag for review
3. Standardize email formats (34 records) - Apply regex

**Short-term (1 week):**
1. Standardize date format across all columns
2. Implement product category validation
3. Deduplicate customer records

**Long-term (1 month):**
1. Add data validation rules in source systems
2. Set up automated quality monitoring
3. Create data quality dashboard

**💰 BUSINESS IMPACT:**
- Clean data = Better analytics accuracy
- Estimated improvement: +15% model performance
- Risk reduction: Prevent wrong business decisions
```

### 9. 🤖 Automated Insights Generation

```
🤖 AI-POWERED INSIGHTS

**AUTOMATED ANALYSIS REPORT**
Generated: August 4, 2026 at 3:22 PM

**🔥 TRENDING NOW:**

1. **📈 Mobile Sales Surge (+47% this week)**
   - iPhone sales up 52% vs last week
   - Android phones up 41% vs last week
   - Likely cause: Back-to-school season + competitor price hike
   - **Action:** Increase mobile inventory by 30%

2. **⚠️ Cart Abandonment Spike (67% → 74%)**
   - Started 3 days ago
   - Affected checkout process timing out
   - **Root cause:** Payment gateway latency increase
   - **Action:** Switch to backup payment processor

3. **🎯 New Customer Segment Identified**
   - "Young Professionals" (25-35, high income, tech buyers)
   - 18% of recent customers, 34% of revenue
   - Currently untargeted in marketing
   - **Opportunity:** Create dedicated campaign

**🔮 PREDICTIONS:**

**Next 7 Days:**
- Sales volume: 89% likely to exceed target
- Top seller: Laptops (73% confidence)
- Risk day: Thursday (payment processing issues)

**Next 30 Days:**
- Revenue forecast: $234,000 ±15%
- New customer acquisition: 1,200 ±200
- Churn rate: 3.2% (within normal range)

**📊 ANOMALIES DETECTED:**

1. **Yesterday's Data:**
   - West region sales dropped 34% (unusual)
   - Investigation: Regional competitor launched promotion
   - Impact: -$12,000 revenue

2. **This Morning:**
   - Website traffic up 67% but conversions flat
   - Possible cause: Viral social media mention
   - **Action:** Capitalize with targeted ads

**💡 RECOMMENDED ACTIONS:**

**High Priority:**
1. Fix payment gateway issue (blocking 7% of purchases)
2. Restock iPhone inventory (will sell out in 2 days)
3. Launch counter-promotion in West region

**Medium Priority:**  
1. A/B test new checkout flow
2. Create "Young Professional" marketing segment
3. Investigate mobile app performance issues

**💬 BUSINESS QUESTIONS TO EXPLORE:**
1. Why is cart abandonment higher on mobile?
2. Can we predict which products will trend next?
3. What's driving the repeat purchase rate increase?
4. Should we expand to the identified customer segment?
```

### 10. 📚 Data Story Generation

```
📚 DATA STORYTELLING

**THE COMEBACK STORY: Q2 2026 PERFORMANCE**

**📖 Executive Summary:**

After a challenging Q1, our e-commerce platform not only recovered but achieved record-breaking performance in Q2 2026. Here's the data-driven story of our turnaround.

**Chapter 1: The Challenge (Q1 2026)**
```
The Dark Period:
- Revenue: $1.2M (down 23% YoY)
- Customer satisfaction: 3.2/5.0
- Cart abandonment: 78% (industry avg: 65%)
- Mobile conversion: 0.8% (desktop: 2.4%)

Key Issues Identified:
🔴 Slow website (4.2s load time)
🔴 Poor mobile experience  
🔴 Limited payment options
🔴 Weak customer support
```

**Chapter 2: The Transformation (April-May)**
```
Actions Taken:
✅ Website optimization (4.2s → 1.1s load time)
✅ Mobile-first redesign
✅ Added 5 new payment methods
✅ 24/7 chat support launched
✅ Personalized recommendations

Investment: $450,000
Timeline: 8 weeks
```

**Chapter 3: The Results (Q2 2026)**
```
🎯 Revenue Growth:
   Q1: $1.2M → Q2: $2.1M (+75% growth!)

📱 Mobile Success:
   Conversion: 0.8% → 2.9% (+262%)
   Mobile revenue share: 28% → 67%

🛒 Customer Experience:
   Cart abandonment: 78% → 52%
   Page load time: 4.2s → 1.1s
   Customer satisfaction: 3.2 → 4.7/5.0

💰 Business Metrics:
   New customers: +89% vs Q1
   Repeat purchase rate: +156%
   Average order value: $84 → $127
   Customer lifetime value: +203%
```

**Chapter 4: The Insights**
```
🔍 What Worked:
1. Mobile-first approach was game-changer
2. Personalization increased AOV by 51%
3. Chat support reduced cart abandonment by 26%
4. Faster site = Higher conversion (+127%)

📊 Key Success Factors:
- Data-driven decision making
- Customer-centric design
- Cross-functional team collaboration
- Continuous testing & optimization

🎯 Unexpected Discoveries:
- Mobile users buy more premium products
- Chat support drives 23% of total sales
- Weekend sales increased 89% (better UX)
- Recommendation engine accuracy: 91%
```

**Chapter 5: Looking Forward**
```
🔮 Q3 Projections:
- Revenue target: $2.8M (+33% vs Q2)
- New market expansion: 3 countries
- Product line extension: 45 new SKUs
- Mobile app launch: September 2026

📈 Growth Drivers:
- AI-powered personalization (Phase 2)
- Voice commerce integration
- Subscription service launch
- B2B marketplace addition

⚠️ Risk Factors:
- Increased competition (+40% new entrants)
- Economic uncertainty impact
- Seasonal demand variation
- Technology scalability challenges
```

**🏆 Key Takeaways for Leadership:**
1. **Speed matters:** 1 second = 7% conversion loss
2. **Mobile is king:** 67% of revenue now mobile
3. **Personalization works:** 91% recommendation accuracy
4. **Support sells:** Chat drives 23% of sales
5. **Data drives growth:** Every decision backed by analytics

**💰 ROI Summary:**
- Investment: $450,000
- Additional Q2 revenue: $900,000  
- **ROI: 200% in 3 months**
- Projected annual impact: $3.6M

*"The data tells a clear story: customer-centric improvements, backed by solid analytics, can drive exponential growth. Our Q2 transformation proves that with the right data insights and swift execution, any business can achieve remarkable results."*

**📊 Supporting Data Dashboard:** [Interactive charts and detailed breakdowns available in the full report]
```

### Response Style

- Lead with visual data representations
- Provide actionable business insights
- Use statistical rigor with clear explanations
- Show confidence intervals and error margins  
- Translate complex analysis to business language
- Always include specific recommendations
- Use emojis for data story flow