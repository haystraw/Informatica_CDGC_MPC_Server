# CDGC Search Query Examples

Reference queries for the CDGC catalog search interface.
Use these as patterns when building new searches.

**Format rules:**
- Each line inside a code block is one complete, standalone query string.
- Prose lines outside code blocks are descriptions or labels, not queries.
- Exceptions are noted inline where a single query spans multiple lines or uses commas internally.

---

## Catalog Source Discovery

Find catalog sources by business term, classification, or policy.
Each line below is a separate, complete query string:

```
catalog sources containing data elements related to business terms related to policies *pii*
catalog sources containing data elements related to business terms 'First Name' and containing data elements related to business terms 'Last Name'
catalog sources containing tables related to Column related to Classification with Name 'Filing Status'
catalog sources containing Data Elements related to Classification with sensitivity in ( High, Medium )
catalog sources containing data elements related to policies 'Auditing Interactions with Consumers'
```

---

## Data Elements

Find data elements by classification, business term, policy, or resource:

```
Data Elements related to Classification with Name 'Email' or 'Birth date'
Data Elements related to Classification with [ Name Address ]
Data Elements related to Classification with sensitivity in ( High, Medium )
Data Elements related to data classification and in resource "Workday"
Data Elements related to Business Term and in resource "NSEN Retail Marketing"
data elements in (resource "NSEN Retail Marketing" or "NSEN Retail Rewards")
```

Find elements with curation status:

```
data elements related with curation status ACCEPTED to data classification
data elements related with curation status ACCEPTED to data classification "OLD First Name"
Data Element related with curation status AUTO_ACCEPTED to Business Term
Data Element related with curation status *ACCEPTED to assets related to Policy "Personal Data"
dq Data Element related with curation status *ACCEPTED to assets related to Policy "Personal Data"
data elements related with curation status NONE to Business Term
```

Available curation statuses: `AUTO_ACCEPTED`, `ACCEPTED`, `REJECTED`, `NONE`
Note: "Pending" Claire recommendations use curation status `NONE`, not `PENDING`.

Find recently modified elements (owned by a specific user):

```
data elements in (catalog source with Stakeholder @"shayes_santander") and Modified on within last 7 days
```

---

## Critical Data Elements (CDEs)

Find CDEs scoped to a resource, dataset, table, or system:

```
Data Elements related to (business terms which are critical data element) and in resource "Files"
Data Elements related to (business terms which are critical data element) and related to technical dataset "Informatica Summary Report"
Data Elements related to (business terms which are critical data element) and related to all related to system "Informatica - Reporting"
Data Elements related to (business terms which are critical data element) and related to dataset "Informatica - Summary Report"
```

---

## Tables and Technical Datasets

Find tables by classification or column properties:

```
tables related to Column related to Classification with Name 'Filing Status'
tables related to (columns which are profiled and in catalog source Mongo*)
tables related to data elements related to datasets
tables related to Column related to Classification with [ Name Address or 'First Name' or 'Address Line 1' or 'Birth date' or City or 'Credit Card' or Email or 'First Name' or Gender or 'Last Name' or 'Phone Number USA' or 'USA City' or 'USA Zip' ]
```

Find technical datasets by policy or classification:

```
Technical Data Sets related to Data Element related to assets related to Policy "United States - HIPAA"
Technical Data Sets related to Data Elements related to Classification with sensitivity in ( High, Medium )
Technical Data Sets related to Data Element related with curation status *ACCEPTED to assets related to Policy "Personal Data"
Technical Datasets related to Data Element related to assets related to Policy "Personal Data"
technical Data Sets in (catalog source with Stakeholder @"shayes_santander") and Modified on within last 7 days
```

---

## Policies

Find assets related to a specific policy:

```
Data Element related to assets related to Policy "United States - HIPAA"
dq rules related to Data Element related to assets related to Policy "United States - HIPAA"
assets related to Data Element related to assets related to Policy "United States - HIPAA"
dq rule related to Data Element related to assets related to Policy "Personal Data"
resource related to all related to Technical Data Sets related to Data Element related to assets related to Policy "Personal Data"
Technical Datasets related to Data Element related to assets related to Policy "Personal Data"
data elements related to business terms related to policies *pii*
```

Find assets using custom attribute (policy name pattern):

```
all where Policies is "*CCPA Policy*"
```

---

## Data Quality Rules

Find DQ rules by resource or element:

```
data quality rule occurrence related to (data elements in (resource "NSEN Retail Marketing" or "NSEN Retail Rewards"))
dq rule related to data elements in resource ( Loan*)
dq rule *Mandatory* and related to data elements in resource ( Loan*)
dq rule related to Data elements related to tables in resource "NSEN Retail Rewards"
dq rule related to Data elements related to tables in resource "NSEN Data Warehouse"
dq rule related to Data elements related to (table NS_MKTG_USER) in resource "NSEN Snowflake Retail Marketing"
dq rule related to Data Element related to assets related to Policy "Personal Data"
dq rule related to Data Elements related to Classification with sensitivity in ( High, Medium )
dq rule related to Data Elements related to assets related to Policy "United States - HIPAA"
```

Find DQ rules by recency:

```
dq rule Modified on within last 1 days
dq rule Modified on within last 20 hours
```

Find DQ rules without a specific stakeholder role:

```
dq rule without stakeholder role @role:"Governance Administrator"
```

---

## Data Quality Rule Occurrences

Find unacceptable DQ results:

```
(data element related to business terms which are critical data element) related to data quality rule occurrence with threshold result "not acceptable"
data quality rule occurrence related to Data Elements related to (business terms which are critical data element)
```

Find DQ occurrences for specific business terms by dimension:

```
(data quality rule occurrence related to data element related to business terms ("Telephone Number", "Email Address", "Address")) dimension Validity
```

Find tables/datasets related to unacceptable validity checks:

```
Technical Datasets related to data element related to (((data quality rule occurrence related to data element related to business terms ("Telephone Number", "Email Address", "Address")) dimension Validity ) with threshold result in ("not acceptable"))
```

Find systems or datasets with bad DQ results:

```
systems containing datasets related to data elements related to dq rule with threshold result in ('not acceptable')
datasets related to data elements related to dq rule with threshold result in ('not acceptable')
```

---

## Classification

Find classification assets by curation status:

```
data classification related with curation status ACCEPTED to asset
Technical Data Sets related related to Column related to Classification with [ Name Address or 'First Name' or 'Address Line 1' or 'Birth date' or City or 'Credit Card' or Email or 'First Name' or Gender or 'Last Name' or 'Phone Number USA' or 'USA City' or 'USA Zip' ]
```

---

## Sensitivity

Find by sensitivity level:

```
Classification with sensitivity in ( High, Medium ) related to Data Element
Data Elements related to Classification with sensitivity in ( High, Medium )
Technical Data Sets related to Data Elements related to Classification with sensitivity in ( High, Medium )
dq rule related to Data Elements related to Classification with sensitivity in ( High, Medium )
catalog sources containing Data Elements related to Classification with sensitivity in ( High, Medium )
```

---

## Stakeholders and Ownership

Find objects without stakeholders assigned:

```
ALL without stakeholder
Data Sets without stakeholder
Glossary without stakeholder
Business asset without stakeholder
dq rule without stakeholder
```

Find all objects owned by a specific user:

```
ALL with Stakeholder @"reinvent01"
ALL with Stakeholder @"reinvent01" and Modified on within last 30 days
```

---

## Profiling

Find profiled columns and their tables:

```
(columns which are profiled and in catalog source Mongo*) related to Table "DEV-ABI_BKP"
tables related to (columns which are profiled and in catalog source Mongo*)
```

---

## Certification

Find certified objects:

```
reports which are certified
all which are certified
all certified by @shayes_compass
dq rule related to Data elements related to tables related to all related to reports which are certified
```

---

## Lineage

Find anything with lineage:

```
all related through core.dataflow to any
all related through core.DataSetDataFlow to any
all related through core.DirectionalDataFlow to any
```

Table-level lineage — what flows into a target resource:

```
(all in resource "NSEN Retail Rewards") related through core.DataSetDataFlow to any
```

Table-level lineage — what flows out of a source resource:

```
all related through core.DataSetDataFlow to (any in resource "NSEN Retail Rewards")
```

Cross-resource lineage (source → target):

```
(all in resource "Cloud Data Integration") related through core.DataSetDataFlow to (any in resource "NSEN Retail Rewards")
```

---

## Multiple Types in One Query

Combine asset types with a comma to return multiple object types in a single search:

```
statement in resource "Informatica - NSEN Retail Marketing",data elements in resource "Informatica - NSEN Retail Marketing"
statement in resource "Snowflake POC",data elements in resource "Snowflake POC"
```

---

## ROPA — Records of Processing Activity

Find all assets related to a ROPA project.
**Note: the following is one single query string** — the commas join multiple sub-expressions into one search, they do not separate individual queries:

```
(datasets related to processes related to project "Records of Processing Activity"),(processes related to project "Records of Processing Activity"),(policies related to processes related to project "Records of Processing Activity"),(project "Records of Processing Activity")
```

---

## Dashboard Queries

### DQ Score Chart (bar chart)

Unacceptable DQ on CDEs:

```
(data element related to business terms which are critical data element) related to data quality rule occurrence with threshold result "not acceptable"
```

PII data elements for bar chart:

```
data elements related to business terms related to policies *pii*
```

### DQ Rules for Specific Resources

```
data quality rule occurrence related to (data elements in (resource "NSEN Retail Marketing" or "NSEN Retail Rewards"))
data elements in (resource "NSEN Retail Marketing" or "NSEN Retail Rewards")
data quality rule occurrence related to (data element related to business terms which are critical data element)
```
