"""Deterministic SYNTHETIC demonstration; no operational mode implied."""
from pathlib import Path
import argparse, hashlib, importlib.metadata, json, platform
import pandas as pd
from modules.mining_scenario import load_scenarios, pressure_index
from modules.pollution import load_observations, exposure_table
from modules.exposure import join_environment
from modules.biological_response import select_response
from modules.risk_assessment import prototype_risk_index
from models.risk_model import fit_ridge
from modules.spatial_model import predict_locations
from modules.validation import cross_validate, validation_metrics
from modules.uncertainty import bootstrap_mean_bands
from gis.preprocessing import spatial_blocks
from gis.mapping import export_mapping_table, export_geojson, plot_map
ROOT=Path(__file__).resolve().parent

def main(output=None,config=None):
    out=Path(output) if output else ROOT/'outputs/demo'
    out.mkdir(parents=True,exist_ok=True)
    cfg_path=Path(config) if config else ROOT/'config/demo.json'
    cfg=json.loads(cfg_path.read_text()); data=ROOT/'data/raw'
    pollution,qa=load_observations(data/'synthetic_pollution_long.csv')
    qa.to_csv(out/'pollution_quality_report.csv',index=False)
    if (qa.severity=='error').any(): raise ValueError('Input errors: see pollution_quality_report.csv')
    if not pollution.data_kind.eq('synthetic').all(): raise ValueError('Demo runner accepts synthetic fixtures only; curate a separate real study workflow')
    scenario=pressure_index(load_scenarios(ROOT/'input_files/mining_scenarios.csv'),cfg['reference_production_tonnes'])
    scenario.to_csv(out/'scenario_activity.csv',index=False)
    train=join_environment(exposure_table(pollution),pd.read_csv(data/'synthetic_environment.csv'),cfg['features'])
    train=select_response(train,pd.read_csv(data/'synthetic_biology.csv'),cfg['response'])
    train['prototype_risk_index']=prototype_risk_index(train,cfg['risk_references'])
    train['index_kind']='synthetic_screening_index_not_formal_risk'
    train.to_csv(out/'processed_observations.csv',index=False)
    model=fit_ridge(train,cfg['features'],cfg['response'],cfg['ridge_alpha'])
    groups=spatial_blocks(train,cfg['spatial_block_degrees'])
    results,folds=cross_validate(train,cfg['features'],cfg['response'],groups=groups,n_splits=cfg['n_folds'],alpha=cfg['ridge_alpha'])
    results['data_kind']='synthetic';results['output_kind']='held_out_model_prediction'
    results.to_csv(out/'spatial_cv_predictions.csv',index=False)
    folds['data_kind']='synthetic';folds.to_csv(out/'validation_folds.csv',index=False)
    pd.DataFrame([dict(**validation_metrics(results),scope='synthetic_software_demonstration_only')]).to_csv(out/'validation_metrics.csv',index=False)
    locations=pd.read_csv(data/'synthetic_prediction_locations.csv')
    pred=predict_locations(model,train,locations,cfg['features'])
    bands=bootstrap_mean_bands(train,locations,cfg['features'],cfg['response'],cfg['n_boot'],cfg['seed'],cfg['ridge_alpha'])
    pred=pd.concat([pred,bands],axis=1)
    pred['response']=cfg['response']
    # Rank by epistemic band width only, explicitly NOT a risk ranking.
    pred['monitoring_priority_demo']=pred.uncertainty.rank(method='min',ascending=False)
    export_mapping_table(pred,out/'spatial_predictions.csv');export_geojson(pred,out/'spatial_predictions.geojson')
    export_geojson(train,out/'observations.geojson')
    for col in ['prediction','uncertainty','monitoring_priority_demo']: plot_map(pred,col,out/(col+'.png'))
    for col in ['Ni_sediment_dry_weight',cfg['response'],'prototype_risk_index']: plot_map(train,col,out/(col+'.png'))
    sources=[*data.glob('*.csv'),ROOT/'input_files/mining_scenarios.csv',cfg_path]
    manifest=dict(status='synthetic demonstration; not validated for operational use',configuration=cfg,
      input_sha256={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
      python=platform.python_version(),versions={p:importlib.metadata.version(p) for p in ['numpy','pandas','scikit-learn','matplotlib']},
      limitations=['No calibrated production-to-pollution link','No formal risk assessment','Bootstrap mean bands exclude residual and structural uncertainty','No Indonesian performance evidence'],
      fold_metric_sd=json.loads(folds[['RMSE','MAE','R2']].std().to_json()))
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(f'SYNTHETIC software demonstration complete: {out}')
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path);parser.add_argument('--config',type=Path)
    args=parser.parse_args();main(args.output,args.config)
