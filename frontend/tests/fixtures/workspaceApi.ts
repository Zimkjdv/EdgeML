import type { ApiRequest } from '../../src/modelEvaluation'
export const jobId = '00000000-0000-4000-8000-000000000025'
export const featureNames = ['狀態','發布','模型名稱','Model Name']
export const dataset = (id:string) => ({id,name:id === 'a' ? '資料集甲' : '資料集乙',original_filename:'中文.csv',row_count:100,column_count:5,created_at:'2026-10-15T00:00:00Z',columns:[...featureNames,'目標'].map(name=>({name,raw_dtype:'float64',ml_type:'numeric',missing_count:0,missing_rate:0,unique_count:4,minimum:1,maximum:9,mean:5,std:2,median:5,mode:'3'}))})
export const model = (id:string) => ({id,name:id === 'a' ? '模型名稱' : '狀態',completed_at:'2026-10-15T00:00:00Z',target_column:'目標',algorithm:'xgboost',problem_type:'regression',status:'draft',validation_r2:0.95,validation_rmse:0.2,test_r2:0.91,test_rmse:0.25,feature_columns:featureNames,evaluation_version:'oof-v2',validation_metrics:{r2:0.95,pearson_r:0.976,mae:0.12,mape:1.8,rmse:0.2,nrmse:0.025,max_error:1.2,target_mean:7.4,fold_rmse_mean:0.19,fold_rmse_std:0.01,fold_mae_mean:0.12,fold_r2_mean:0.94},test_metrics:{r2:0.91,pearson_r:0.96,mae:0.15,rmse:0.25},settings:{},manifest:{features:featureNames.map(name=>({name,dtype:'float64',required:true}))}})
// Synthetic, browser-only fixture: no real API, DB, files, model artifacts or tokens.
export function fixtureApi(storage:Storage = localStorage, record:(url:string)=>void = ()=>{}):ApiRequest {
  return async <T>(url:string, init?:RequestInit):Promise<T> => {
    record(url)
    const delay = /\/(datasets|trained-models)\/a$/.test(url) ? 650 : 15
    await new Promise<void>((resolve,reject)=>{ const timer=setTimeout(resolve,delay); init?.signal?.addEventListener('abort',()=>{clearTimeout(timer); reject(new DOMException('Cancelled','AbortError'))},{once:true}) })
    let result:unknown = []
    if (url === '/api/datasets') result = [dataset('a'),dataset('b')]
    else if (url === '/api/trained-models') result = [model('a'),model('b')]
    else if (/\/datasets\/[ab]$/.test(url)) result = dataset(url.at(-1)!)
    else if (/\/trained-models\/[ab]$/.test(url)) result = model(url.at(-1)!)
    else if (url.includes('/preview')) result = {columns:featureNames,rows:[['狀態','發布','模型名稱','Model Name']],total_rows:1,offset:0,limit:50}
    else if (url === '/api/training/jobs' && init?.method === 'POST') {storage.setItem('edgeml-test-job-status','running'); result={id:jobId}}
    else if (url.includes('/training/jobs/')) { const status=storage.getItem('edgeml-test-job-status') || 'running'; result={id:jobId,status,progress:status==='completed'?100:35,message:'測試訓練工作',result_model_id:'b'} }
    else if (url === '/api/models') result = [{id:'b',name:'狀態',version:'1.0.0',framework:'sklearn',problem_type:'regression',target:'目標',description:'fixture',features:featureNames.map(name=>({name,dtype:'float64',required:true}))}]
    else if (url.includes('/feature-importance')) result = {model_name:model(url.includes('/a/')?'a':'b').name,metric:'rmse',data_source:'training',sample_count:100,repeats:3,baseline_score:0.2,computed_at:'2026-10-15T00:00:00Z',rankings:featureNames.map((feature,index)=>({rank:index+1,feature,importance:0.4/(index+1),std:0.01})),publication:{status:'unpublished'}}
    return structuredClone(result) as T
  }
}
