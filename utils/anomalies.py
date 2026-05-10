import pandas as pd
import numpy as np
from scipy.stats import zscore, chisquare
from sklearn.ensemble import IsolationForest

def check_ballot_reconciliation(df_units):
    """
    Refined ballot reconciliation that filters out empty/NaN clerical errors 
    from actual mathematical impossibilities (Fraud).
    """
    df = df_units.copy()
    
    # 1. Flag Clerical Errors (Missing Data)
    clerical_mask = df[['Voters_Showed_Up', 'Used_Ballots', 'Valid_Ballots']].isna().any(axis=1) | (df['Voters_Showed_Up'] == 0)
    
    # Process only rows that have actual numerical data
    df_clean = df[~clerical_mask].copy()
    
    # 2. Flag Mathematical Fraud
    ghost_voting = df_clean['Used_Ballots'] > df_clean['Voters_Showed_Up']
    math_mismatch = df_clean['Used_Ballots'] != (df_clean['Valid_Ballots'] + df_clean['Invalid_Ballots'] + df_clean['No_Vote_Ballots'])
    over_100_turnout = df_clean['Turnout_Pct'] > 100

    df_clean['Anomaly_Type'] = ""
    df_clean.loc[ghost_voting, 'Anomaly_Type'] += "Ghost Voters; "
    df_clean.loc[math_mismatch, 'Anomaly_Type'] += "Math Mismatch; "
    df_clean.loc[over_100_turnout, 'Anomaly_Type'] += "Turnout > 100%; "
    
    failed_units = df_clean[df_clean['Anomaly_Type'] != ""]
    clerical_units = df[clerical_mask].copy()
    clerical_units['Anomaly_Type'] = "Missing/Zero Data (Clerical)"
    
    return failed_units[['Unit_ID', 'District', 'Subdistrict', 'Voters_Showed_Up', 'Used_Ballots', 'Anomaly_Type']], clerical_units[['Unit_ID', 'District', 'Subdistrict', 'Voters_Showed_Up', 'Used_Ballots', 'Anomaly_Type']]

def calculate_isolation_forest(df_units):
    """
    Advanced Multivariate Anomaly Detection using Machine Learning.
    Evaluates Turnout, Invalid Ballot Rate, and No Vote Rate simultaneously.
    """
    df = df_units.dropna(subset=['Turnout_Pct', 'Invalid_Pct', 'No_Vote_Ballots']).copy()
    
    # Calculate No Vote Percentage
    df['No_Vote_Pct'] = (df['No_Vote_Ballots'] / df['Used_Ballots']) * 100
    df['No_Vote_Pct'].fillna(0, inplace=True)
    
    # Select features for the model
    features = ['Turnout_Pct', 'Invalid_Pct', 'No_Vote_Pct']
    X = df[features]
    
    # Train Isolation Forest (contamination = 0.02 assumes ~2% of units might be anomalous)
    clf = IsolationForest(n_estimators=100, contamination=0.02, random_state=42)
    df['Anomaly_Score'] = clf.fit_predict(X)
    df['Anomaly_Severity'] = clf.decision_function(X) # Lower score = more anomalous
    
    # Filter for anomalies (Score == -1)
    anomalies = df[df['Anomaly_Score'] == -1].sort_values(by='Anomaly_Severity')
    
    return anomalies[['Unit_ID', 'Subdistrict', 'Turnout_Pct', 'Invalid_Pct', 'No_Vote_Pct', 'Anomaly_Severity']]

def detect_symmetric_vote_buying(df_party, df_const):
    """
    Detects the 'Double-X' (กาเบอร์เดียวกัน) vote-buying effect.
    Cross-references Constituency results with Party-List results.
    """
    if df_party.empty or df_const.empty:
        return pd.DataFrame()
    
    df_party = df_party.copy()
    df_const = df_const.copy()

    # FIX: Normalize Unit_IDs for merging by stripping out differing file tags
    # This turns 'KK10_CONST_โนนศิลา...' and 'KK10_PARTY_โนนศิลา...' into 'KK10_โนนศิลา...'
    df_party['Merge_ID'] = df_party['Unit_ID'].str.replace('_CONST', '', regex=False).str.replace('_PARTY', '', regex=False)
    df_const['Merge_ID'] = df_const['Unit_ID'].str.replace('_CONST', '', regex=False).str.replace('_PARTY', '', regex=False)
    
    # 1. Get the #1 Constituency Candidate per unit (using the new Merge_ID)
    top_const = df_const.sort_values(['Merge_ID', 'Score'], ascending=[True, False]).drop_duplicates('Merge_ID')
    top_const = top_const[['Merge_ID', 'Entity_Number', 'Entity_Name']].rename(columns={
        'Entity_Number': 'Candidate_Number', 
        'Entity_Name': 'Candidate_Name'
    })
    
    # 2. Calculate average baseline for every Party-List party
    df_party['Party_Mean'] = df_party.groupby('Entity_Number')['Score'].transform('mean')
    df_party['Party_Std'] = df_party.groupby('Entity_Number')['Score'].transform('std').replace(0, np.nan)
    df_party['Party_Spike_Z_Score'] = (df_party['Score'] - df_party['Party_Mean']) / df_party['Party_Std']
    
    # 3. Merge Constituency Winner info into the Party List scores on the normalized ID
    merged = pd.merge(df_party, top_const, on='Merge_ID', how='inner')
    
    # 4. Filter for 'Double-X' criteria: Party Number == Local Candidate Number
    matched_data = merged[merged['Entity_Number'] == merged['Candidate_Number']]
    matched_data = matched_data.sort_values(by='Party_Spike_Z_Score', ascending=False)
    
    # Rename Entity columns back to Party context for final output
    matched_data = matched_data.rename(columns={
        'Entity_Number': 'Party_Number', 
        'Entity_Name': 'Party_Name'
    })
    
    return matched_data[['Unit_ID', 'Party_Name', 'Party_Number', 'Candidate_Name', 'Score', 'Party_Spike_Z_Score']]
def calculate_turnout_zscores(df_units):
    """
    Calculates the Z-Score for voter turnout to find statistical outliers.
    """
    df = df_units.dropna(subset=['Turnout_Pct']).copy()
    df['Turnout_Z_Score'] = zscore(df['Turnout_Pct'])
    
    # Filter for standard deviation > 3 (extreme outliers)
    outliers = df[df['Turnout_Z_Score'].abs() > 3]
    return outliers.sort_values(by='Turnout_Z_Score', ascending=False)

def calculate_benfords_law(df_scores):
    """
    Applies Benford's Law to the first digit of every valid score.
    """
    # Filter out 0 scores as they do not have a leading digit 1-9
    valid_scores = df_scores[df_scores['Score'] > 0].copy()
    
    # Extract the first digit as an integer
    valid_scores['First_Digit'] = valid_scores['Score'].astype(str).str[0].astype(int)
    
    # Calculate observed frequencies
    observed_counts = valid_scores['First_Digit'].value_counts().sort_index()
    total_scores = observed_counts.sum()
    observed_pct = (observed_counts / total_scores) * 100
    
    # Calculate expected frequencies using Benford's formula
    digits = np.arange(1, 10)
    expected_pct = np.log10(1 + 1/digits) * 100
    
    results = pd.DataFrame({
        'Digit': digits,
        'Expected_Pct': expected_pct,
        'Observed_Pct': observed_pct.reindex(digits, fill_value=0)
    })
    
    # Calculate Chi-Square P-Value to determine statistical significance
    expected_counts = (expected_pct / 100) * total_scores
    chi2_stat, p_val = chisquare(f_obs=observed_counts.reindex(digits, fill_value=0), f_exp=expected_counts)
    
    return results, p_val