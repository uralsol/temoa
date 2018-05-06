
from pyomo.environ import *
from pyomo.core import Objective, Var, Constraint
from pyomo.opt import SolverFactory
import sys, os
from matplotlib import pyplot as plt
import numpy as np
from IPython import embed as IP
from temoa_model import temoa_create_model
from temoa_initialize import DemandConstraintErrorCheck
from temoa_rules import PeriodCost_rule

from IPython import embed as IP

def pf_result(dat,dat1):
    M = temoa_create_model()
    M.num_scenarios                = Param()
    M.scenario                     = Set(ordered=True, rule=lambda M: range(1, value(M.num_scenarios) + 1))
    M.CapacityFactorTechMultiplier = Param(M.scenario)
    M.FixedCostMultiplier          = Param(M.scenario)
    M.phi                          = Param()

    data1 = DataPortal(model = M)
    data1.load(filename=dat)
    data1.load(filename=dat1)
    instance = M.create_instance(data1)
    Cost = []
    for scenario in sorted(instance.scenario.keys()):
        M.del_component('Capacity_Constraint')
        M.del_component('PeriodCost_rule')

        def PeriodCost_rule ( M, p ):
            P_0 = min( M.time_optimize )
            P_e = M.time_future.last() # End point of modeled horizon
            GDR = value( M.GlobalDiscountRate )
            MLL = M.ModelLoanLife
            MPL = M.ModelProcessLife
            x   = 1 + GDR    # convenience variable, nothing more.
        
            loan_costs = sum(
                M.V_Capacity[S_t, S_v]
              * (value( M.CostInvest[S_t, S_v] )
                * value( M.LoanAnnualize[S_t, S_v] )
                * ( value( M.LifetimeLoanProcess[S_t, S_v] ) if not GDR else
                    (x **(P_0 - S_v + 1) * (1 - x **(-value( M.LifetimeLoanProcess[S_t, S_v] ))) / GDR)))
              * ((1 -  x**( -min( value(M.LifetimeProcess[S_t, S_v]), P_e - S_v ) ))
                  /(1 -  x**( -value( M.LifetimeProcess[S_t, S_v] ) ) ))
              for S_t, S_v in M.CostInvest.sparse_iterkeys()
              if S_v == p)
        
            fixed_costs = sum(
                M.V_Capacity[S_t, S_v]
              * (value( M.CostFixed[p, S_t, S_v] ) * value(M.FixedCostMultiplier[scenario])
                * ( value( MPL[p, S_t, S_v] ) if not GDR else
                    (x **(P_0 - p + 1) * (1 - x **(-value( MPL[p, S_t, S_v] ))) / GDR)))
              for S_p, S_t, S_v in M.CostFixed.sparse_iterkeys()
              if S_p == p)
        
            variable_costs = sum(
                M.V_ActivityByPeriodAndProcess[p, S_t, S_v]
              * (value( M.CostVariable[p, S_t, S_v] )
                * ( value( MPL[p, S_t, S_v] ) if not GDR else
                    (x **(P_0 - p + 1) * (1 - x **(-value( MPL[p, S_t, S_v] ))) / GDR)))
        
              for S_p, S_t, S_v in M.CostVariable.sparse_iterkeys()
              if S_p == p)
            period_costs = (loan_costs + fixed_costs + variable_costs)
            return period_costs

        def Capacity_Constraint ( M, p, s, d, t, v):
            if t in M.tech_hourlystorage:
                return Constraint.Skip   
            produceable = (
              (   value( M.CapacityFactorTech[s, d, t] ) * value(M.CapacityFactorTechMultiplier[scenario])
                * value( M.CapacityToActivity[ t ] )
                * value( M.SegFrac[s, d]) )
                * value( M.ProcessLifeFrac[p, t, v] )
              * M.V_Capacity[t, v]
            )
            expr = (produceable >= M.V_Activity[p, s, d, t, v])
            return expr        
        
        M.CapacityConstraint           = Constraint( M.ActivityVar_psdtv, rule=Capacity_Constraint )
        instance = M.create_instance(data1)

        optimizer = SolverFactory('cplex')
        results = optimizer.solve(instance)
        instance.solutions.load_from(results)
        Cost.append(value(instance.TotalCost))


    scenario_cost = open("ScenarioCost.dat", "w") #create a new file
    print >> scenario_cost, """\
    data;
    
    param: scenarioCost  :=
        # scenario        #cost
    """
    for scenario in sorted(instance.scenario.keys()):
        print >> scenario_cost, "    %10g    %10s    " % \
                (scenario, Cost[scenario - 1])
    
    print >> scenario_cost, "    ;\n"
    scenario_cost.close()
    return Cost


def temoa_robust(dat, dat1, dat2):
    M = temoa_create_model()
    def Robust_rule ( M ):
        regret = sum(M.regret[scenario] for scenario in M.scenario)
        risk = value(M.phi) * (sum((M.z[p,s,d,dem,scenario] * M.z[p,s,d,dem,scenario]) for p,s,d,dem,scenario in M.DemandConstraint))
        
        return (regret + risk)

    def Demand_Constraint ( M, p, s, d, dem, scenario ):
        supply = sum(
          M.V_FlowOut[p, s, d, S_i, S_t, S_v, dem]
    
          for S_t, S_v in M.helper_commodityUStreamProcess[ p, dem ]
          for S_i in M.helper_ProcessInputsByOutput[ p, S_t, S_v, dem ]
        ) 
    
        DemandConstraintErrorCheck( supply, p, s, d, dem )
    
        expr = (supply + M.z[p, s, d, dem, scenario] == M.Demand[p, dem] * M.DemandSpecificDistribution[s, d, dem] )
    
        return expr

    def Capacity_Constraint ( M, p, s, d, t, v, scenario):
    
        if t in M.tech_hourlystorage:
            return Constraint.Skip
            
        produceable = (
          (   value( M.CapacityFactorTech[s, d, t] ) * value(M.CapacityFactorTechMultiplier[scenario])
            * value( M.CapacityToActivity[ t ] )
            * value( M.SegFrac[s, d]) )
            * value( M.ProcessLifeFrac[p, t, v] )
          * M.V_Capacity[t, v]
        )
    
        expr = (produceable >= M.V_Activity[p, s, d, t, v])
        return expr

    def regret_Constraint(M, scenario):
        expr = (M.regret[scenario] == sum( PeriodCost_rule(M, p, scenario) for p in M.time_optimize ) - value(M.scenarioCost[scenario]))
        return expr

    def real_obj(M): #STOCH ELASTIC
        a = sum( PeriodCost_rule(M, p, scenario)  
            for p in M.time_optimize 
            for scenario in M.scenario)
        expr = (a >= 0)
        return expr

    def PeriodCost_rule ( M, p, scenario ):
        P_0 = min( M.time_optimize )
        P_e = M.time_future.last() # End point of modeled horizon
        GDR = value( M.GlobalDiscountRate )
        MLL = M.ModelLoanLife
        MPL = M.ModelProcessLife
        x   = 1 + GDR    # convenience variable, nothing more.
    
        loan_costs = sum(
            M.V_Capacity[S_t, S_v]
          * (value( M.CostInvest[S_t, S_v] )
            * value( M.LoanAnnualize[S_t, S_v] )
            * ( value( M.LifetimeLoanProcess[S_t, S_v] ) if not GDR else
                (x **(P_0 - S_v + 1) * (1 - x **(-value( M.LifetimeLoanProcess[S_t, S_v] ))) / GDR)))
          * ((1 -  x**( -min( value(M.LifetimeProcess[S_t, S_v]), P_e - S_v ) ))
              /(1 -  x**( -value( M.LifetimeProcess[S_t, S_v] ) ) ))
          for S_t, S_v in M.CostInvest.sparse_iterkeys()
          if S_v == p)
    
        fixed_costs = sum(
            M.V_Capacity[S_t, S_v]
          * (value( M.CostFixed[p, S_t, S_v] ) * value(M.FixedCostMultiplier[scenario])
            * ( value( MPL[p, S_t, S_v] ) if not GDR else
                (x **(P_0 - p + 1) * (1 - x **(-value( MPL[p, S_t, S_v] ))) / GDR)))
          for S_p, S_t, S_v in M.CostFixed.sparse_iterkeys()
          if S_p == p)
    
        variable_costs = sum(
            M.V_ActivityByPeriodAndProcess[p, S_t, S_v]
          * (value( M.CostVariable[p, S_t, S_v] )
            * ( value( MPL[p, S_t, S_v] ) if not GDR else
                (x **(P_0 - p + 1) * (1 - x **(-value( MPL[p, S_t, S_v] ))) / GDR)))
    
          for S_p, S_t, S_v in M.CostVariable.sparse_iterkeys()
          if S_p == p)
        period_costs = (loan_costs + fixed_costs + variable_costs)
        return period_costs

        
    M.del_component('TotalCost')
    M.del_component('DemandConstraint')
    M.del_component('M.DemandActivityConstraint_psdtv_dem_s0d0')
    M.del_component('DemandActivityConstraint')
    M.del_component('Capacity_Constraint')
    M.del_component('PeriodCost_rule')
    # Efficiency: all the parameters
    M.num_scenarios                = Param()
    M.scenario                     = Set(ordered=True, rule=lambda M: range(1, value(M.num_scenarios) + 1))
    M.CapacityFactorTechMultiplier = Param(M.scenario)
    M.FixedCostMultiplier          = Param(M.scenario)
    M.z                            = Var(M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario)
    M.regret                       = Var(M.scenario)
    M.phi                          = Param()
    M.scenarioCost                 = Param(M.scenario)
    
    M.TotalCost                    = Constraint(rule=real_obj)
    M.DemandConstraint             = Constraint( M.time_optimize, M.time_season, M.time_of_day, M.commodity_demand, M.scenario, rule=Demand_Constraint )
    M.CapacityConstraint           = Constraint( M.ActivityVar_psdtv, M.scenario, rule=Capacity_Constraint )
    M.regret_Constraint            = Constraint(M.scenario, rule=regret_Constraint)

    M.Robust = Objective(rule=Robust_rule, sense=minimize)

    data1 = DataPortal(model = M)
    data1.load(filename=dat)
    data1.load(filename=dat1)
    data1.load(filename=dat2)
    instance = M.create_instance(data1)

    optimizer = SolverFactory('cplex')
    results = optimizer.solve(instance)
    instance.solutions.load_from(results)
    return instance


def Robust_run():
    model = temoa_create_model()
    #dat = '/mnt/disk2/nspatank/Efficiency_nonlinear/data_files/US_National_ELC.dat'
    dat = '/mnt/disk2/nspatank/EEfficiency_uptodate/data_files/test_Simple.dat'
    dat1 = '/mnt/disk2/nspatank/EEfficiency_uptodate/data_files/scenarios_CFFOM.dat'
    scenario_cost = pf_result(dat, dat1)
    dat2 = '/mnt/disk2/nspatank/EEfficiency_uptodate/temoa_model/ScenarioCost.dat'
    instance = temoa_robust(dat, dat1, dat2)
 
    fp = open('results.csv', 'w')
    dm = open('demand.csv', 'w')
    print >>fp, '\"', instance.name, '\"'
    print >>fp, '\"Model Documentation: ', instance.doc, '\"'
    print >>fp, '\"Solver Summary\"'
    # Objective
    print >>fp, '\"Objective function is:', value(instance.Robust), '\"'
    print >>fp, '\"Total Cost is:', value(instance.TotalCost.body), '\"'
    for v in instance.component_objects(Var, active=True):
        varobject = getattr(instance, str(v))
        #IP()
        print >> fp, ""
        print >> fp, "\"Variable: %s\", \"Notes: %s\"" % (v, varobject.doc)
        print ("fixing"+str(v))
        for index in varobject:
            varobject[index].fixed = True
            print>>fp, "\"" + str(index) + "\"", varobject[index].value


if __name__ == "__main__":
    Robust_run()
    sys.stdout.write('\a\a')
    sys.stdout.flush()