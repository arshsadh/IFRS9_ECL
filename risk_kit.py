import pandas as pd
import numpy as np
from itertools import takewhile
import scipy.stats as stats
import cvxpy as cp
import gc
import re
import plotly.graph_objects as go
import ipywidgets as widgets
from rich.console import Console
console = Console()

# Main computation functions : ————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————
def cholesky_decomposition(data = None, uniform_correlation= None, matrix_order = None, correlation_matrix = None):

    if data is None:
        raise ValueError("No data provided")
    if matrix_order is None:
        raise ValueError("Matrix size not provided")

    if uniform_correlation is None and correlation_matrix is None : 
        raise ValueError("Provide either a uniform correlation value or the correlation matrix between variables")
   
    corr = np.full((matrix_order,matrix_order),uniform_correlation)
    np.fill_diagonal(corr,1)
    
    chol = np.linalg.cholesky(corr)
    ncols = data.shape[0]
    
    data = stats.norm.ppf(data) #  inverse of the cumulative distribution function for the normal distribution.
    corr_values = pd.DataFrame(np.matmul(chol, data)).T
    
    corr_data= pd.DataFrame(stats.norm.cdf(corr_values))
    
    return corr_data

def fq_rating_estimation(runs,borrower_val, rating_estimation=True, initial_probation = 0, probabilities = None,  return_history = False, transition_matrix = None,
                        rating_list = None, bucket_list = None):
    
    # This is used to get the first reported quarter rating estimate.
    
    """
    The function runs a markov chain simulation for 1st reported quarter given the Sanction rating.
    The parameters of the function are : 
    
    - runs : Required, Scalar value 
             Takes in the number between the sanction date and the first reporting date, accepts positive integers only
    - borrower_val : a scalar str value, 
          Can be either the Sanction rating of the counterparty or the bucket at the time of Sanction, ie., "Current"
    - rating_estimation : Required; Boolean Value, default : True ; 
                          The function by defaults computes the rating transitions, setting to False would compute the DPD transition.
    - initial_probation : default 0 ; 
                          The parameter extracts the number of periods remaining on the probation if the account was marked as "D"
                          during the probation_period check. 
                          
                          For example, if account was marked as "D"/ 90+ DPD in the 2nd last quarter, and the probation period is 4 period, the parameter
                          would take 2 signifying that the remaining period. If the account was defaulted in the last quarter, a direct probation period of 4
                          would apply.
    - probabilities : Required ; A list of transition probabilities for the markov simulation. The length must be equal to the number of runs.
    - return_history : Optional, Default : False, Returns a list,
                       To get the list of all past estimates upto the current estimate of DPD/ Rating, set the variable to True.
    - transition_matrix : Required; The Transition matrix against which the probabilities needs to be compared. The transition must be a cumulative transition matrix.
    - rating_list : Optional ; The list of ratings as defined by the institution. This variable needs to be provided if rating_estimation is set as True.
    - bucket_list : The list of buckets as defined by the institution. This variable needs to be provided if rating_estimation is set as False.

    * The function returns atmost 2 sets of values : A list and a scalar value depending on the return_history argument. By default, the return_history is set as False and
    only the estimated period value is returned.

    """
    chosen_vals = []
    probability = []
    probability = probabilities
    
    historical_estimates = []
    
    borrower_val = borrower_val # DPD or Rating
    
    if rating_estimation ==True:
        matrix = transition_matrix # cumulative_transition_matrix # Use of the TTC - Transition matrix to get the Credit Rating
        vector = rating_list #ratings
    else:
        matrix = transition_matrix # cumulative_dpd_transition_matrix # Use of DPD TTC - transition Matrix 
        vector = bucket_list #buckets
        
    for i  in range(runs): # The number of loops (or quarterrs) the simulation needs to run.

        cumulative_probs = matrix.loc[borrower_val].values
        
        random_draws = np.atleast_1d(probabilities[i]) #np.random.rand(1)
        
        indices = np.searchsorted(cumulative_probs, random_draws)
        
        chosen_vals = [vector[j]  for j in indices] # Mapping indices back to original ratings or DPD bucket
        
        historical_estimates.append(chosen_vals)
        
        borrower_val = chosen_vals[-1] # Updating the borrower rating for the next iteration
        
        # Updating the rating for next iteration: 
        return_val = borrower_val

    if return_history ==True : 
        return return_val, historical_estimates 
    else:
        return return_val # Returns a Single rating or DPD bucket.

def rating_estimation(runs, borrower_val , reporting_date, scenario= None, rating_estimation = True, required_probation_period = None, dpd = None, initial_probation_count = 0,
                      probabilities = None, return_history = False,
                      date_range = None, transition_matrices = None, rating_list = None, bucket_list = None, delinq_bucket_check = None, delinq_rating="D"): 
    
    """
    The function runs a markov chain simulation for rating grades given the first reporting period rating.
    The parameters are : 
    
    - runs = Takes in the number of quarters the estimation needs to be done, accept positive integers only
    
    - borrower_val = The previous period rating of the counterparty / DPD bucket of the counterparty
    
    - reporting_date = Should be in datetime format and it should exist in the data the analysis is being done.
    
    - scenario = The corresponding scenarios 
    - rating_estimation = True, The function by defaults computes the credit rating transitions, setting to False would compute the DPD bucket transition.
    
    - required_probation_period : optional* scalar value
        This signifies the number of periods a borrower stays in the default caategory after clearning previous dues.
    
    - dpd : A list of DPD values estimated for the markov simulation. The length must be equal to the value of `runs` argument.
    
    - initial_probation_count : The probation count from the first reported quarter, default value of 0.
    
    - probabilities : A list of transition probabilities for the markov simulation. The length must be equal to the value of `runs` argument.
    
    - return_history : default : False, Returns a list,
                       To get the list of all past estimates upto the current estimate of DPD/ Rating, set the variable to True.
    
    - date_range : The period over which the values needs to be estimated.
    - transition_matrices : A dictionary of Point-in-time transition matrices where keys are named in the following format : 
                            {date_scenario}, 
                            where :
                            i.  date format should be "%Y-%m-%d"
                            ii. scenario value should match that of the scenario argument
    - rating_list : Optional ; The list of ratings as defined by the institution. This variable needs to be provided if rating_estimation is set as True.
    - bucket_list : The list of buckets as defined by the institution. This variable needs to be provided if rating_estimation is set as False.
    - delinq_bucket_check : The delinquency bucket at or after the institution deems the borrower as defaulter.
    - delinq_rating : Default : "D"
                     The delinquency rating that is assigned once the borrower is deemed as a Defaulter
                     
    * The function uses "D" to mark the accounts as Defaulters. Make sure the transition matrices being used are named correctly to match that of the function.
    
    """
    
    ret_vals = []
    chosen_vals = []
    act_dict = {}
    
    probation_flag = False
    
    historical_estimates = []
    
    dates = date_range
    
    borrower_val  = borrower_val
    
    if rating_estimation == True : 
        act_dict =  transition_matrices #pit_tm_dict
        vector = rating_list # ratings
    else:
        act_dict = transition_matrices # pit_dpd_tm_dict
        vector = bucket_list # buckets
    
    if required_probation_period is None : # Getting the DPD bucket estimations : 
    
        for i in range(runs):
            
            random_draws = np.atleast_1d(probabilities[i])
            
            date = dates[i]
            date = date.strftime("%Y-%m-%d")
            dict_key = date + "_" + scenario
            
            matrix = act_dict[dict_key] # Getting the PIT- Transition matrix
            cumulative_probs = matrix.loc[borrower_val].values # Extracting the respective probabilites given the rating/ DPD Bucket
            
            indices = np.searchsorted(cumulative_probs, random_draws)
            
            chosen_vals = [vector[j] for j in indices] # Mapping indices back to original ratings
            
            # Updating the rating for next iteration: 
            borrower_val = chosen_vals[-1]
            ret_vals.extend(chosen_vals)
            
        return ret_vals
    
    
    elif required_probation_period is not None:
    # Getting the Credit rating estimation, would need the DPD bucket estimation here for the override based on the probation period.
        
        if borrower_val == delinq_rating:
            if dpd[0] == delinq_bucket_check :
                probation_count = required_probation_period
                probation_flag = True
            else:
                probation_count = initial_probation_count
                probation_flag = True
                    
        elif borrower_val != delinq_rating:
            if dpd[0] == delinq_bucket_check :
                probation_count = required_probation_period
                probation_flag = True
            else:
                probation_count = initial_probation_count
        
        for i in range(runs):
            
            if  dpd[i] == delinq_bucket_check :  # Check 1 : If current DPD is 90+, the rating is forced to be "D". 
                ret_vals.extend(delinq_rating)
                borrower_val = delinq_rating
                probation_count= required_probation_period
                
            elif probation_count > 0 :
                chosen_vals = delinq_rating
                ret_vals.extend(chosen_vals)
                borrower_val = chosen_vals
                
                probation_count -= 1
        
            else:
                    
                random_draws = np.atleast_1d(probabilities[i])

                date = dates[i]
                date = date.strftime("%Y-%m-%d")
                dict_key = date + "_" + scenario
                
                matrix = act_dict[dict_key] # Getting the PIT- Transition matrix
                
                cumulative_probs = matrix.loc[borrower_val].values # Extracting the respective probabilites given the rating/ DPD Bucket
                
                indices = np.searchsorted(cumulative_probs, random_draws)
                
                chosen_vals = [vector[j] for j in indices] # Mapping indices back to original ratings
                
                historical_estimates.append(chosen_vals)
                
                probation_time = required_probation_period
                
                temp_ratings = []
                
                if chosen_vals[-1]==delinq_rating:
                    if dpd[i] != delinq_bucket_check: # "90+ DPD": # If rating estimate comes out to be "D" but the current DPD is not 90+, rating is re-estimated.
                        
                        iterations = 0
                        default_rng = np.random.default_rng(seed = 21)
                        while True:
                            
                            random_draws = np.atleast_1d(default_rng.random())

                            indices = np.searchsorted(cumulative_probs, random_draws)
                            
                            chosen_vals = [vector[j] for j in indices]
                            temp_ratings.append(chosen_vals)
                            
                            if chosen_vals[-1] != delinq_rating:
                                break
                        
                        borrower_val = chosen_vals[-1] # temp_vals[-1]
                        ret_vals.append(borrower_val)
                else:
                    borrower_val = chosen_vals[-1]
                    ret_vals.append(borrower_val)
        
        if return_history == True:
            return ret_vals, historical_estimates
        else:
            return ret_vals


# ———————————————————————————————— 
def ECL_sim(dataset = None, iteration_start = None, iteration_end = None, iterations=1, dpd_at_start = "Current", CCF = None, LGD = None, rho = 0.12, delinq_rating="D", delinq_bucket_check = "90+ DPD", 
            required_probation_period = 2, sicr_trigger = 1.5, scen = None, pd_map = None, lambda_map = None, buckets_dict = None, ScenarioWeights = None, 
            segment_chargeoff_caps=None, cumulative_dpd_transition_matrix = None , cumulative_transition_matrix = None , pit_dpd_tm_dict = None , pit_tm_dict = None,
           buckets = None, rating_order = None, rho_CCF = 0.12, rho_LGD = 0.12, return_result_data=False) :
# ————————————————————————————————
    
    """
    
    dataset: The dataset on which the ECL computation needs to be performed.

    iteration_start : The starting position number of the iteration. The function includes the starting value.
    iteration_end : The ending position number of the iteration. The function excludes the ending value.
    iterations : The total number of iterations that needs to be performed.
    
    dpd_at_start : Default : "Current"
                   The DPD bucket at the time when the loan was originated/ Sanctioned. The value must match the value of the transition matrix being provided.
    
    CCF : Required;
          A Dictionary with keys as the types of Segment and values as the CCF percentage.

    LGD : Required;
          A Dictionary with keys as the types of Segment and values as the LGD percentage.

    rho:  Default value of 12%;
          The asset correlation value used to compute Point-in-time Probability of Default.
    
    delinq_rating : Default value - "D"
                    The flag used by the institution to mark a borrower as a defaulter. Make sure it matches with that of the transition matrix.
    
    delinq_bucket_check : Default value : 90+ DPD
                       The DPD bucket at or after which the institution classifies the loan as a default. The value must match the value of the transition matrix being provided.
                       
    required_probation_period : Default value of 2 period;
                                The number of quarters for which the account stays in probation after curing.
                                
    sicr_trigger: Default value of 150%,
                  The threshold value above which the account is marked to have a Significant increase in credit risk.
                  
    scen : List ; A list of scenarios used for the ECL computation. 
    
    pd_map : Series ; A series of values containing the rating grades and their corresponding 1 year Probability of default values.
    
    lambda_map : Series ; A series of values containing the rating grades and their corresponding hazard rate value. This is used for computing PIT- PD.
    
    buckets_dict : Dictionary ; A dictionary of buckets where {key : value} pair represents the {index : bucket}

    ScenarioWeights : Dictionary;
                      The weights for each scenario ordered as {Scenario:Weight}.
                      
    segment_chargeoff_caps : Dictionary;
                             The number of period after which the loan is shifted to charge off given a consecutive count the loan stayed in default.
                             
    cumulative_dpd_transition_matrix :
    cumulative_transition_matrix : 
    pit_dpd_tm_dict : 
    pit_tm_dict :
    
    buckets : List; 
              The days past due (DPD) buckets specified by the institution. The buckets must match with the transition matrices used for DPD estimation.
    rating_order : List; 
                  The credit rating grades specified by the institution. The grades must match with the transition matrices used for rating estimation.
    rho_CCF :Scalar; Default value of 12%
              The asset correlation used to compute PIT-CCF.
              
    rho_LGD : Scalar; Default value of 12%
              The asset correlation used to compute PIT-LGD.
              
    * sicr_trigger is computed by taking the ratio of the PD at the time of reporting date and the PD at the time of sanction date.
    
    """
    if dataset is None:
        raise FileNotFoundError("No dataset provided")
    if iterations ==0:
        raise ValueError("The number of iterations cannot be 0")
    
    seed_value_dict = {}
    books_MC = {}
    
    Scenario_Estimates_dict = {}

    Iterations_df = []
    Iteration_results_ECL = pd.DataFrame() # Stores the Final Scenario and weighted ECL values for each iteration concatenated by dates.
    
    period_list = ["Historical_DPD", "Estimated_DPD","Historical_Rating","Estimated_Rating"]
    
    #  Dataset Columns :  ———> Used later to delete unwanted columns to save memory consumption when running multiple iterations
    cols = dataset.columns.to_list()
    reporting_date_col_idx = cols.index("Reporting_Date")
    Customer_ID_col_idx = cols.index("Customer_ID")
    colstoDrop = cols[Customer_ID_col_idx+1:reporting_date_col_idx] + cols[reporting_date_col_idx+1:]
    
    # ——————————————
    # Generating the list of seed values
    # ——————————————
    startVal = iteration_start
    stopVal = iteration_end
    
    for p in period_list:
        seed_value_dict[f"{p}_seedVal"] = np.arange(start = startVal, stop = stopVal)
        startVal+=100
        stopVal+=100
    
    seed_arr_loc_Val = 0 # The array index location value to fetch the seed for the particular iteration : 
    
    for r in range(iteration_start, iteration_end):
    
        # Generating the different lists of estimates that we would be needing throughout the estimation process: 
        for s in scen:
            listNames = ["estimated_rating_", "dpd_bucket_", "probation_time_", "DPD_EAD_counter_","reporting_90dpd_count_"]
            for l in listNames:
                keyVal = f"{l}{s}"
                if keyVal==f"probation_time_{s}":
                    Scenario_Estimates_dict[keyVal] = 0
                else:
                    Scenario_Estimates_dict[keyVal] = []

        current_rating = []
        previous_dpd = []
        est_rating = []
        chosen_vals = []
        dpd_bucket = []
        dpd_vals  = []
        
        historical_dpd = []
        
        sanction_probation_count = 0
        trial_list = []        
        
        # The probation period as set by the risk committee. Change this variable as needed. Each increment in number would indicate 1 quarter. 
        # For example, required_probation_period = 2 means a probation period of 2 quarters is applicable
        
        temp =[]
                
        counts = []
        
        rating = None
        
        local_seed_dpd = np.random.default_rng(seed=seed_value_dict["Historical_DPD_seedVal"][seed_arr_loc_Val] if iterations!=1 else 42)
        probabilities_dpd = local_seed_dpd.random(dataset[dataset["Quarter_Index"]==0]["Quarter_Count"].sum())
        
        local_seed_rating = np.random.default_rng(seed=seed_value_dict["Historical_Rating_seedVal"][seed_arr_loc_Val] if iterations!=1 else 52)
        probabilities_rating = local_seed_rating.random(dataset[dataset["Quarter_Index"]==0]["Quarter_Count"].sum())

        # —————— Inducing Correlation Between DPD and Rating :
        Rawdata = pd.DataFrame([probabilities_dpd,probabilities_rating])
        
        result = cholesky_decomposition(data= Rawdata,uniform_correlation = 0.80, matrix_order = 2)
        
        probabilities_dpd = np.array(result.iloc[:,0])
        probabilities_rating = np.array(result.iloc[:,1])

        # —————— 
        local_seed_sanction_rating = np.random.default_rng(seed=seed_value_dict["Estimated_Rating_seedVal"][seed_arr_loc_Val]if iterations!=1 else 72)
        probabilities_sanction_rating = local_seed_sanction_rating.random(dataset["Q_Count_for_Rating_Est."].sum())
        
        local_seed_sanction_dpd = np.random.default_rng(seed=seed_value_dict["Estimated_DPD_seedVal"][seed_arr_loc_Val] if iterations!=1 else 95)
        probabilities_sanction_dpd = local_seed_sanction_dpd.random(dataset["Q_Count_for_Rating_Est."].sum())

        # ——————  Inducing Correlation Between DPD and Rating :
        Rawdata = pd.DataFrame([probabilities_sanction_dpd,probabilities_sanction_rating])
        
        result = cholesky_decomposition(data= Rawdata,uniform_correlation = 0.80, matrix_order = 2)
        
        probabilities_sanction_dpd = np.array(result.iloc[:,0])
        probabilities_sanction_rating = np.array(result.iloc[:,1])
        
        seed_arr_loc_Val += 1 # Increasing the counter by one for the next iteration.
        
        n = 0
        quarter_count_est = 0
        
        forecast_quarter_count_est = 0 
        
        trimmed_dataset_q0_q1 = dataset[dataset["Quarter_Index"]<=1]
        for n in trimmed_dataset_q0_q1.index:
        #for n in range(len(dataset)):
            
            if dataset.loc[n,"Quarter_Index"] ==0 :
                  
                if dataset.loc[n,"Q_Count_for_Rating_Est."] == 0 :
                    current_rating = dataset.loc[n,"Origination_Rating"]

                    for s in scen:
                        Scenario_Estimates_dict[f"estimated_rating_{s}"].append(current_rating)
                        
                        Scenario_Estimates_dict[f"dpd_bucket_{s}"].append(dpd_at_start)          # DPD Starts at the Current State for newly originated Loans

                        # probation_time for base, optimistic and pessimistic scenario would be 0 here.
                        Scenario_Estimates_dict[f"probation_time_{s}"] = 0

                        # dpd_counter for EAD : 
                        Scenario_Estimates_dict[f"DPD_EAD_counter_{s}"].append(0)
                        
                else:
                    rep_date = dataset.loc[n,"Reporting_Date"]
                    Quarter_runs = dataset.loc[n,"Q_Count_for_Rating_Est."]
                    orig_rating = dataset.loc[n,"Origination_Rating"]

# ———————————————————— Making the code dynamic for "n" scenarios : 
                    
                    for s in scen : 
                        probabilities = probabilities_sanction_dpd[quarter_count_est:quarter_count_est+Quarter_runs+1]

                        # ------- DPD Estimation :
                        dpd_bucket, historical_dpd = fq_rating_estimation(runs=Quarter_runs, borrower_val = dpd_at_start, #"Current",
                                                                             rating_estimation = False,
                                                                             probabilities = probabilities, return_history=True, 
                                                                             transition_matrix = cumulative_dpd_transition_matrix,
                                                                             bucket_list = buckets)
                        
                        Scenario_Estimates_dict[f"dpd_bucket_{s}"].append(dpd_bucket)
        
                        # ---------- DPD Counter for EAD computation : 
                        temp = [item for sublist in historical_dpd for item in sublist] # Creating a flat list out of the sublist
                        
                        count = sum(1 for _ in takewhile(lambda x: x == delinq_bucket_check, reversed(temp)))
                        chosen_val = count 
                        Scenario_Estimates_dict[f"DPD_EAD_counter_{s}"].append(chosen_val)
                        
                        # ---------- Rating Estimation : 
                        
                        Scenario_Estimates_dict[f"probation_time_{s}"] = 0
                        last_90_position = None  # how many periods ago was the last 90+
                        
                        for index, d in enumerate(historical_dpd[-required_probation_period:][::-1]):
                            if d[0] == delinq_bucket_check:
                                last_90_position = index  # 0 ==> last quarter, 1 ==> 2 quarters ago
                                rating = delinq_rating # "D"
                                break
                            else:
                                rating = None
                        
                        if last_90_position is not None:
                            Scenario_Estimates_dict[f"probation_time_{s}"] = required_probation_period - last_90_position
                            Scenario_Estimates_dict[f"probation_time_{s}"] = max(0, Scenario_Estimates_dict[f"probation_time_{s}"])
                                    
                        if rating is None:
                            probabilities = probabilities_sanction_rating[quarter_count_est : quarter_count_est + Quarter_runs + 1]
                            
                            est_rating = fq_rating_estimation(runs = Quarter_runs, borrower_val = orig_rating, rating_estimation=True, probabilities = probabilities,
                                                                 transition_matrix = cumulative_transition_matrix, rating_list = rating_order)
                            
                            Scenario_Estimates_dict[f"estimated_rating_{s}"].append(est_rating)
                        else:
                            Scenario_Estimates_dict[f"estimated_rating_{s}"].append(rating)
                        
                        
                    # —— Used to slice the probabilities lists
                    quarter_count_est += Quarter_runs
            
            elif dataset.loc[n,"Quarter_Index"] == 1 :
                
                Quarter_runs = dataset.at[n,"Quarter_Count"] 
                rep_date = dataset.at[n,"Reporting_Date"] 
                
                date_range = pd.date_range(start = rep_date, periods = Quarter_runs, freq="QE") # QE- Quarter End dates ; Change if needed.
                
                for s in scen : 
                    # ---------- DPD Bucket Estimation : 
                    previous_dpd = Scenario_Estimates_dict[f"dpd_bucket_{s}"][-1]
                    
                    probabilities = probabilities_dpd[forecast_quarter_count_est: forecast_quarter_count_est+ Quarter_runs]
                    
                    dpd_bucket = rating_estimation(runs=Quarter_runs, borrower_val = previous_dpd, reporting_date = rep_date, scenario=f"{s}", rating_estimation = False,
                                                      probabilities = probabilities, date_range = date_range, transition_matrices = pit_dpd_tm_dict, bucket_list = buckets)
                    
                    Scenario_Estimates_dict[f"dpd_bucket_{s}"].extend(dpd_bucket)
                    
                    # Counter for reporting Period ( 90 + DPD count+=1 else 0)
                    
                    c =  Scenario_Estimates_dict[f"DPD_EAD_counter_{s}"][-1] # Adjust the starting value 
                    counts = [(c := c + 1 if item == delinq_bucket_check else 0) for item in dpd_bucket]
                    Scenario_Estimates_dict[f"reporting_90dpd_count_{s}"].append(counts)
                    
                    # --------- Rating : 
                    previous_rating = Scenario_Estimates_dict[f"estimated_rating_{s}"][-1]
                    
                    dpd_vals = Scenario_Estimates_dict[f"dpd_bucket_{s}"][-Quarter_runs:]
                    
                    probabilities = probabilities_rating[forecast_quarter_count_est: forecast_quarter_count_est + Quarter_runs]
                    
                    est_rating = rating_estimation(runs = Quarter_runs, borrower_val = previous_rating, reporting_date = rep_date, scenario =f"{s}",
                                                      rating_estimation = True, required_probation_period = required_probation_period,
                                                      dpd = dpd_vals,
                                                      initial_probation_count = Scenario_Estimates_dict[f"probation_time_{s}"],
                                                      probabilities = probabilities, date_range = date_range, transition_matrices = pit_tm_dict, rating_list = rating_order,
                                                      delinq_bucket_check = delinq_bucket_check, delinq_rating="D"
                                                     )
                    
                    Scenario_Estimates_dict[f"estimated_rating_{s}"].extend(est_rating)
                    
                forecast_quarter_count_est += Quarter_runs
            
        
            #else:
            #    continue

            
        for s in scen:
            
            dataset[f"Estimated_Rating_{s}"] = Scenario_Estimates_dict[f"estimated_rating_{s}"]
            dataset[f"DPD Bucket_{s}"] = Scenario_Estimates_dict[f"dpd_bucket_{s}"]

            dataset[f"Lambda_{s}"] = dataset[f"Estimated_Rating_{s}"].map(lambda_map)        
            
            #------- DPD EAD Counter for first reporting period : (Used to compute EAD values)
            Scenario_Estimates_dict[f"reporting_90dpd_count_{s}"] = [item for sublist in Scenario_Estimates_dict[f"reporting_90dpd_count_{s}"] for item in sublist]
            
            dataset[f"DPD_EAD_counter_{s}"] = [buckets_dict[val] for val in dataset[f"DPD Bucket_{s}"]] # Mapping the dictionary values based on the DPD estimation column
        
            # Adjusting the value for Quarter_Index ==0 : 
        
            dataset.loc[dataset["Quarter_Index"]==0,f"DPD_EAD_counter_{s}"] = Scenario_Estimates_dict[f"DPD_EAD_counter_{s}"]
            dataset.loc[dataset["Quarter_Index"]!=0,f"DPD_EAD_counter_{s}"] = Scenario_Estimates_dict[f"reporting_90dpd_count_{s}"]
        
            # # Resetting the counter for all except 90+ DPD cells (See the documentation for more information)
            dataset[f"DPD_EAD_counter_{s}"] = np.where(dataset[f"DPD Bucket_{s}"]!= delinq_bucket_check,
                                                                 [buckets_dict[val] for val in dataset[f"DPD Bucket_{s}"]],  
                                                       
                                                                 dataset[f"DPD_EAD_counter_{s}"])
     
        # —————————————————————————————————————————————————————————————————
        # SICR Trigger : 
        # —————————————————————————————————————————————————————————————————
                
        idiosyncratic_risk_factor = np.sqrt(1-rho)
        
        # PD as per Sanction Rating:
        dataset["PD_Sanction"] = dataset["Origination_Rating"].map(pd_map)/100
        
        # Tenure for revolving loans (used for computing lifetime PD) : 
        tenure_revolving = 3 # 3 years
        
        dataset["CCF %"] = dataset["Segment"].map(CCF)
        dataset["LGD %"] = dataset["Segment"].map(LGD)
        
        for s in scen:
            # --------------------PD at the time of reporting : 
            
            dataset[f"PD1yr_{s}"] = np.where(dataset[f"Estimated_Rating_{s}"]!=delinq_rating, #"D",
                                                      dataset[f"Estimated_Rating_{s}"].map(pd_map),1)
        
                                                   
            dataset[f"PD1yr_{s}"] = np.where(dataset[f"Estimated_Rating_{s}"]!=delinq_rating,
                                                      stats.norm.cdf((stats.norm.ppf(dataset[f"PD1yr_{s}"]/100)- rho*dataset[f"Z_{s}"])/idiosyncratic_risk_factor),
                                                      1)
                
            # -----------STAGE CLASSIFICATION : 
            
            dataset[f"Stage_{s}"] = np.where(((dataset[f"Estimated_Rating_{s}"]==delinq_rating) & (dataset[f"DPD Bucket_{s}"]==delinq_bucket_check))
                                             | ((dataset[f"Estimated_Rating_{s}"]==delinq_rating) & (dataset[f"DPD Bucket_{s}"]!=delinq_bucket_check)),3,
                                              np.where(((dataset[f"PD1yr_{s}"]/dataset["PD_Sanction"])-1 >= sicr_trigger),2
                                                       ,1)) # Stage 1
                
            # ----------- PD COMPUTATION AS PER STAGING :
            
            dataset[f"PD_{s}"]= np.where(dataset[f"Stage_{s}"]==3,
                                                  1, # 100% PD irrespective of the type of loan
                                                  np.where((dataset[f"Stage_{s}"]==2) & (dataset[f"Estimated_Rating_{s}"]!=delinq_rating),
                                                           np.where(dataset["Type_of_Loan"]!="Revolving",
                                                                    # Lifetime PD for Amortising and Bullet loans :
                                                                    stats.norm.cdf((stats.norm.ppf(1-np.exp(-dataset[f"Lambda_{s}"]*dataset["Year_left"]))-rho*dataset[f"Z_{s}"])/idiosyncratic_risk_factor),
                                                                    ## Lifetime PD for revolving loans :
                                                                     stats.norm.cdf((stats.norm.ppf(1-np.exp(-dataset[f"Lambda_{s}"]*tenure_revolving))-rho*dataset[f"Z_{s}"])/idiosyncratic_risk_factor))
                                                           ,
                                                           np.where((dataset[f"Stage_{s}"]==2) & (dataset[f"Estimated_Rating_{s}"]==delinq_rating),1, # 100% PD
                                                                    dataset[f"PD1yr_{s}"])
                                                          )
                                                 )
        
            # ------ PIT- CCF Computation : 
            dataset[f"CCF_{s}"] = stats.norm.cdf((stats.norm.ppf(dataset["CCF %"]/100) - np.sqrt(rho_CCF)*dataset[f"Z_{s}"])/np.sqrt(1-rho_CCF))
        
            # ------ PIT- LGD Comutation :
            dataset[f"LGD_{s}"] = stats.norm.cdf((stats.norm.ppf(dataset["LGD %"]/100) - np.sqrt(rho_LGD)*dataset[f"Z_{s}"])/np.sqrt(1-rho_LGD))
        
        # ———————————— EAD Computation : 
        
        monthly_rate = dataset["Origination_Interest_Rate"]/12
        t = dataset["Tenure"]
        n = dataset["MOB"] # -3 # To get the previous quarter balance, we subtract 3 months.
        
        # ————————————————————————————————————
        # Segment Caps : 
        # ————————————————————————————————————
        
        if segment_chargeoff_caps is None :
            segment_chargeoff_caps = {key:2 for key in dataset["Segment"].unique()}  # Default Cap of 180 days or 2 quarters 
    
        
        segment_cap = dataset["Segment"].map(segment_chargeoff_caps).fillna(2) # default cap set to 2 quarters

        # ————————————————————————————————————
        # • Bullet loans :
        # ————————————————————————————————————
        
        prev_drawn = dataset.groupby("Customer_ID")["Outstanding_Balance"].shift(1).fillna(dataset["Outstanding_Balance"])

        for s in scen :
            
            dpd_ead_counter = dataset[dataset["Type_of_Loan"]=="Bullet"][f"DPD_EAD_counter_{s}"]
            segment_capped_dpd_EADcounter = np.minimum(dpd_ead_counter,segment_cap) # The final counter values to be used!
            
            # dpd_ead_counter = dataset[f"DPD_EAD_counter_{s}"]
            # segment_capped_dpd_EADcounter = np.minimum(dpd_ead_counter,segment_cap) # The final counter values to be used!
            
            dataset[f"EAD_{s}"] = np.where(dataset["Type_of_Loan"]=="Bullet",
                                                np.where((dataset[f"DPD Bucket_{s}"]=="30-59 DPD") | (dataset[f"DPD Bucket_{s}"]=="60-89 DPD"),
                                                         (dataset["Sanction_Amount (in USD)"]*((1+(dataset["Origination_Interest_Rate"]/12))**segment_capped_dpd_EADcounter)),
                                                         np.where(dataset[f"DPD Bucket_{s}"]=="90+ DPD",
                                                                  (dataset["Sanction_Amount (in USD)"]*((1+(dataset["Origination_Interest_Rate"]/12))*(segment_capped_dpd_EADcounter*3))),
                                                                  dataset["Sanction_Amount (in USD)"])),0)
        
        # ———————————————————————————————————— 
        # • Amortising Loans 
        # ———————————————————————————————————— 
            
        amort_results = {s : [] for s in scen} # Dictionary to store list of EAD values for each scenario
            
        amort_data = dataset[dataset["Type_of_Loan"]=="Amortising"].reset_index(drop=True) # Subset of the loan Dataset containing only amortising type loans
            
        segment_cap_amort = amort_data["Segment"].map(segment_chargeoff_caps).fillna(2) # default cap set to 2
            
        for s in scen:
            dpd_ead_counter = amort_data[f"DPD_EAD_counter_{s}"]
            segment_capped_dpd_EADcounter = np.minimum(dpd_ead_counter,segment_cap_amort) # The final counter values to be used!
            
            for idx in range(len(amort_data)):
            
                dpd_bucket = amort_data.at[idx, f"DPD Bucket_{s}"]
                segment = amort_data.at[idx,"Segment"]
                segment_map_val = segment_chargeoff_caps[segment] # Getting the segment level charge off period 
                
                if dpd_bucket==dpd_at_start : # "Current":
                        amort_results[s].append(amort_data.at[idx,"Outstanding_Balance"])
                    
                else:
                    
                    if amort_data.at[idx,f"DPD_EAD_counter_{s}"]>segment_map_val : # Capping the EAD value
                        
                        if amort_data.at[idx, "Quarter_Index"] == 0 :
                            
                            pmt = amort_data.at[idx,"PMT"]
                            monthly_interest = amort_data.at[idx,"Origination_Interest_Rate"]/12
                            t = amort_data.at[idx,"Tenure"]
                            n = amort_data.at[idx,"MOB"]
                            
                            ipmt_count = segment_map_val # the K quarter step to go backwards
                            ipmt_count = (ipmt_count * 3 if dpd_bucket == "90+ DPD" else ipmt_count) 
                            # Adjusting the value for 90+ DPD (3 months), such that each 90+ DPD reperesents the number of months to go backwards.
                            
                            # Principal Outstanding computation : 
                            principal_due = pmt*((1-(1+monthly_interest)**-(t-(n-ipmt_count-1)))/monthly_interest)
                            
                            # IPMT Calculation :
                            total_ipmt_val = 0
                            
                            for i in range(1,ipmt_count+1):
                                ipmt = -pmt*((1+monthly_interest)**(n-1-i-t)-1)
                                total_ipmt_val = total_ipmt_val + ipmt
            
                            # EAD COmputation : 
                            ead = total_ipmt_val + principal_due
                            amort_results[s].append(ead)
                            
                        else:
                            amort_results[s].append(amort_results[s][-1])
                        
                    else:
        
                        pmt = amort_data.at[idx,"PMT"]
                        monthly_interest = amort_data.at[idx,"Origination_Interest_Rate"]/12
                        t = amort_data.at[idx,"Tenure"]
                        n = amort_data.at[idx,"MOB"]
        
                        ipmt_count = segment_capped_dpd_EADcounter.at[idx] # the K quarter steps to go backwards
                        ipmt_count = (ipmt_count * 3 if dpd_bucket == "90+ DPD" else ipmt_count) 
                        # Adjusting the value for 90+ DPD (3 months), such that each 90+ DPD reperesents the number of months to go backwards.
        
                        # Principal Outstanding computation : 
                        principal_due = pmt*((1-(1+monthly_interest)**-(t-(n-ipmt_count-1)))/monthly_interest)
                        
                        # IPMT Calculation :
                        total_ipmt_val = 0
                        
                        for i in range(1,ipmt_count+1):
                            ipmt = -pmt*((1+monthly_interest)**(n-1-i-t)-1)
                            total_ipmt_val = total_ipmt_val + ipmt
        
                        # EAD COmputation : 
                        ead = total_ipmt_val + principal_due
                        amort_results[s].append(ead)

        # ————————————————————————————————————     
        # • Revolving loans 
        # ———————————————————————————————————— 
        
        revol_results = {s : [] for s in scen} # Dictionary list to store revolving loans EAD value for each scenario.
        
        revol_data = dataset[dataset["Type_of_Loan"]=="Revolving"].reset_index(drop=True)
        
        segment_cap_revol = revol_data["Segment"].map(segment_chargeoff_caps).fillna(2) # default cap set to 2 (2 quarters)
        
        drawn = revol_data["Outstanding_Balance"]
        sanction = revol_data["Sanction_Amount (in USD)"]
        
        monthly_interest = revol_data["Origination_Interest_Rate"]/12
        
        lagged_balance = revol_data.groupby("Customer_ID")["Outstanding_Balance"].shift(1)
        
        for s in scen:
            
            dpd_bucket = revol_data[f"DPD Bucket_{s}"]
            dpd_ead_counter = revol_data[f"DPD_EAD_counter_{s}"]
            segment_capped_dpd_EADcounter = np.minimum(dpd_ead_counter, segment_cap_revol)
            ccf = revol_data[f"CCF_{s}"]
            
            target_quarter = revol_data["Quarter_Index"] - segment_capped_dpd_EADcounter
            target_quarter = target_quarter.clip(lower=0)   # never look further back than this loan's first row
            
            # simple lookup: for each (Customer_ID, target_quarter), fetch that row's Outstanding_Balance
            lookup_series = revol_data.set_index(["Customer_ID", "Quarter_Index"])["Outstanding_Balance"]
            anchor_balance = lookup_series.reindex(list(zip(revol_data["Customer_ID"], target_quarter))).values
            anchor_balance = pd.Series(anchor_balance, index=revol_data.index)
            
            for idx in range(len(revol_data)):
                bucket = dpd_bucket.at[idx]
                segment = revol_data.at[idx,"Segment"]
                segment_map_val = segment_chargeoff_caps[segment] # Getting the segment capped scalar value
                
                k_month = segment_capped_dpd_EADcounter.at[idx]
                k_month = (k_month*3 if bucket =="90+ DPD" else k_month)
                
                if dpd_ead_counter.at[idx] > segment_map_val:
                    if revol_data.at[idx,"Quarter_Index"]==0:
                        due_amount = drawn.at[idx] * (1+ monthly_interest.at[idx])**k_month # segment_map_val
                        revol_results[s].append(due_amount)
                    
                    else:
                        revol_results[s].append(revol_results[s][-1])
                    
                elif bucket in ("30-59 DPD", "60-89 DPD"):
                    due_amount = drawn.at[idx] * (1 + monthly_interest.at[idx]) ** k_month # segment_capped_dpd_EADcounter.at[idx]
                    revol_results[s].append(due_amount)
                
                elif bucket == dpd_at_start : #"Current":
                    due_amount = drawn.at[idx] + (ccf.at[idx] * (sanction.at[idx] - drawn.at[idx]))
                    revol_results[s].append(due_amount)
                
                elif bucket == "90+ DPD":
                    due_amount = anchor_balance.at[idx] * (1 + monthly_interest.at[idx]) ** k_month
                    revol_results[s].append(due_amount)
        
        # Inserting the EAD values for Amortising and Revolving loans as per scenario :
        for s in scen:
            dataset.loc[dataset["Type_of_Loan"]=="Amortising",f"EAD_{s}"] = amort_results[f"{s}"]
            dataset.loc[dataset["Type_of_Loan"]=="Revolving",f"EAD_{s}"] = revol_results[f"{s}"]
            
            # —————————————————————      
            #  • ECL Computation : 
            # —————————————————————      
            
            dataset[f"ECL_{s}"] = (dataset[f"PD_{s}"]* dataset[f"LGD_{s}"] * dataset[f"EAD_{s}"])/dataset["EIR_Compounding_Factor"] 
        
        dataset["Weighted_ECL"] = sum([dataset[f"ECL_{s}"]*ScenarioWeights[s] for s in scen])
        
        del amort_results, revol_results, amort_data, revol_data
        
        """
        After the Rating and DPD bucket estimation was conducted, it was noted that some loans among the three scenarios were brought in which had higher consecutive
        ounts of 90+ DPD (as high as 44 quarters). These loans would be directly removed from ECL computation and are transferred to Charge off book where the loans would be 
        tracked for recoveries. (The Charge off modelling is out of the scope of this model).
        
        This exercise is not something that would be done with a real bank data, where accounts that are beyond the period after which the bank books the lossses, would not be 
        used in the ECL model.
        
        The above exercise would be performed for all three scenarios seperately.
        
        """
        
        books = {}
        
        active_book_data = pd.DataFrame()
        charge_off_book_data = pd.DataFrame()
        segment_dictionary_data = {}

        for idx, s in enumerate(scen) :
            active_book_data = None
            charge_off_book_data = None
    
            for segment in dataset["Segment"].unique():
                specific_segment_cap = segment_chargeoff_caps[segment]
                # Getting the specific data :
                temp_data = dataset[(dataset["Segment"]==segment)]
                
                # Generating the trigger and the charge_off flag : 
                trigger = (temp_data[f"DPD Bucket_{s}"] == delinq_bucket_check) & (temp_data[f"DPD_EAD_counter_{s}"] >= specific_segment_cap)
                charge_off_flag = trigger.groupby(temp_data["Customer_ID"]).cummax()

                # Creating a temorary dictionary to save the segment's separated data : 
                
                segment_dictionary_data[s] = {"active" : temp_data[~charge_off_flag],
                                              "charge_off" : temp_data[charge_off_flag],
                                             }

                # Re merging the data into the final segregated active and charge off once the data is separated by charge off as per segment : 
                active_book_data = pd.concat([active_book_data,segment_dictionary_data[s]["active"]],axis = 0)
                charge_off_book_data = pd.concat([charge_off_book_data,segment_dictionary_data[s]["charge_off"]], axis = 0)
        
        
            scenario_remove = scen[:idx] + scen[idx + 1:]
            strexp = "".join(f"_{val}|" for val in scenario_remove).removesuffix("|")
            
            cols_to_include = f"^(?:Customer_ID|Reporting_Date|ECL_{s}|Estimated_Rating_{s}|Stage_{s}|DPD Bucket_{s}|Weighted_ECL)"        
            active_book_data = active_book_data.loc[:,active_book_data.columns.str.contains(cols_to_include)]
            charge_off_book_data = charge_off_book_data.loc[:,charge_off_book_data.columns.str.contains(cols_to_include)]
        
            books[s] = {
                "active": active_book_data,
                "charge_off": charge_off_book_data}
        
        # ——— Creating a Dataframe to store the ECL values by reporting date and then appending it to a master df : 
        
        df = pd.DataFrame([books[f"{s}"]["active"].groupby("Reporting_Date")[f"ECL_{s}"].sum() for s in scen]).T
        df["Weighted_ECL"] = sum([df[f"ECL_{s}"]*ScenarioWeights[s] for s in scen])

        Iterations_df.append(df)
                
        # ——— Generating a Master log of all iterations dataframes that are generated for each iteration.
        
        if return_result_data == True :
            books_MC[f"Iteration_{r}"] = {f"{s}" : books[s] for s in scen}
    
    Iteration_results_ECL = pd.concat(Iterations_df,axis=0)
        
    if return_result_data == True:
        return books_MC,Iteration_results_ECL
    else:
        return Iteration_results_ECL

# ——————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

def matrix_optimisation(matrix, default_rates=None, total_investment_grades_cols = 0, diagonal_constraints = True, monotonicity_constraint = True, fix_default_rates = False):

    """
    Smoothing the values of a square matrix.
    
    `Parameters`
    
    matrix : The square matrix that needs to be optimised / scaled.
    
    default_rates : Optional;
                    Takes in a list of default probabilities of ratings upto the "default" definition category to set the constraint.

    total_investment_grades_cols : The total number of investment grade ratings there are in the matrix, inclusive.
                                   This argument sets a hard boundary that a "D" rated borrower cannot transition to an investment grade rating.
    
    diagonal_constraints : Default is set to be True.
                           This sets the monotonicity constraints, such that the diagonal elements in the matrix decrease as we move downwards.
    monotonicty_constraints : Default is set to be True.
                              This sets the monotonicity constraints, such that the values farter away from the diagonal decreases both vertically and horizontally.
    
    fix_default_rates : Default is set to be False.
                        Set the parameter as True if you want to provide a pre determined default probabilities of each rating grade.
    
    """

    if matrix.shape[0] != matrix.shape[1]:
        raise ValueError("The matrix should be a square matrix")

    if (fix_default_rates == True) & (default_rates == None) :
        raise ValueError("Fixed default probabilities are not provided, but the `fix_default_rates` argument is set as True.")
        
    n = matrix.shape[0] 
    X = cp.Variable((n, n))  # the fitted matrix itself — no flattening needed
    
    constraints = [
        cp.sum(X, axis=1) == 1,   # every row sums to 1
        X >= 0, X <= 1,           # valid probabilities
    ]
    # ——————————————
    # Constrint 1  {Diagonal Constraint} :
    # ——————————————
    if diagonal_constraints == True:
        for i in range(len(matrix)-1):
            constraints.append(X[i,i] >= X[i+1,i+1] + 0.01)
    
    # ————————————————
    # Constraint 2 : Monotonicity Constraint : 
    # ————————————————
    
    # A. Row wise Constraint    
    diagCounter = 0
    if monotonicity_constraint ==True : 
        for i in range(len(matrix)):
            colidx = 0 # Resetting the value to iterate each column in a given row.
            c = diagCounter
            for _ in range(len(matrix)-1):
                if i == len(matrix)-1:
                    if colidx <= total_investment_grades_cols :
                        constraints.append(X[i,colidx] == 0)
                else:
                    if c > 0 :
                        constraints.append(X[i,colidx] <= X[i,colidx+1] - 0.0001)
                    else:
                        constraints.append(X[i,colidx] >= X[i,colidx+1] + 0.0001)
                c -=1
                colidx+=1
            diagCounter+=1
    
    # B. Column Wise Constraint : 
        diagCounter = 0
        for i in range(len(matrix)-1):
            c = diagCounter
            for j in range(len(matrix)-1):
                
                multiplier =  -1 if c > 0 else 1
                if c > 0:
                     constraints.append(X[j,i] <= X[j+1,i] - 0.0001)
                else:
                    constraints.append(X[j,i] >= X[j+1,i] + 0.0001)
                c-=1
            
            diagCounter+=1

    # ——————————
    # Constraint 4 Summed Value :
    # ——————————
    
    for i in range(n):
        constraints.append(X[i].sum() == 1)
    
    # ——————————
    # Constraint 5 The "D" Column (or last Column) values must stay as is for all ratings upto CCC.
    # ——————————
    
    if fix_default_rates == True:
        for i in range((n)-1):
            #print(i)
            constraints.append(X[i,-1] == default_rates[i]/100)
    
    # ——————————
    # Mandatory Constraint : All values in the matrix must be non negative.
    # ——————————
    
    constraints.append(X>=0.00)

    # ————————————————————————————————————————

    # Optimisation : 
    
    objective = cp.Minimize(cp.sum_squares(X - matrix.values))
    
    problem = cp.Problem(objective, constraints)
    problem.solve(solver = cp.CLARABEL)
    
    fitted_matrix = pd.DataFrame(X.value, index=matrix.columns, columns=matrix.columns)
    print("Status:", problem.status)
    print("Row sums:", fitted_matrix.sum(axis=1).values)
    fitted_matrix = fitted_matrix.clip(lower=0.00,upper=1)
    
    return fitted_matrix