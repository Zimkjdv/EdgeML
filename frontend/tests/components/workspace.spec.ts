import { describe, it, expect, vi } from 'vitest'
import { effectScope, ref, nextTick, defineComponent, h, provide } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { useLatestTask } from '../../src/composables/useLatestTask'
import { useTrainingJob, TRAINING_JOB_KEY } from '../../src/composables/useTrainingJob'
import { useWorkspace } from '../../src/composables/useWorkspace'
import { useWorkspaceRoute } from '../../src/composables/useWorkspaceRoute'
import { workspaceKey, type Workspace } from '../../src/workspaceContext'
import { ApiError, createApiClient } from '../../src/apiClient'
import DatasetPage from '../../src/pages/DatasetPage.vue'
import TrainedModelsPage from '../../src/pages/TrainedModelsPage.vue'
import { fixtureApi, jobId, featureNames, model } from '../fixtures/workspaceApi'
import type { ApiRequest } from '../../src/modelEvaluation'

function deferred<T>() { let resolve!:(value:T)=>void;const promise=new Promise<T>(yes=>resolve=yes);return {promise,resolve} }
describe('latest request lifecycle',()=>{
  it('native skip-to-content anchors do not replace the active page',async()=>{
    history.replaceState(null,'','/#trained')
    const scope=effectScope(), page=scope.run(()=>useWorkspaceRoute())!
    location.hash='workspace-content';window.dispatchEvent(new HashChangeEvent('hashchange'));await nextTick()
    expect(page.value).toBe('trained');scope.stop()
  })
  it('aborts stale requests, ignores out-of-order success/error and cancels on scope disposal',async()=>{
    const scope=effectScope(), task=scope.run(()=>useLatestTask())!, a=deferred<string>(), b=deferred<string>(), commit=vi.fn(); let signal!:AbortSignal
    const first=task.run(s=>{signal=s;return a.promise},commit), second=task.run(()=>b.promise,commit)
    expect(signal.aborted).toBe(true);b.resolve('B');await second;a.resolve('A');await first
    expect(commit.mock.calls).toEqual([['B']]);const late=deferred<string>();const running=task.run(()=>late.promise,commit);scope.stop();late.resolve('C');await running;expect(commit).toHaveBeenCalledTimes(1)
  })
  it('typed client preserves signals/CSRF, handles empty responses and validation errors',async()=>{
    const signal=new AbortController().signal, fetcher=vi.fn().mockResolvedValueOnce(new Response(null,{status:204})).mockResolvedValueOnce(new Response(JSON.stringify({detail:[{msg:'Invalid column'}]}),{status:422}))
    const api=createApiClient(fetcher);expect(await api('/api/test',{signal})).toBeUndefined();expect(fetcher.mock.calls[0][1].signal).toBe(signal)
    await expect(api('/api/test')).rejects.toMatchObject({status:422,message:'Invalid column'})
  })
})

describe('resumable training job',()=>{
  it('persists job ID only, stops on leave/unmount, resumes once and clears completed job',async()=>{
    vi.useFakeTimers();const enabled=ref(true), done=vi.fn(), failed=vi.fn(), scope=effectScope();let status='running'
    const api=vi.fn(async()=>({status,progress:45,message:'working',result_model_id:'b'})) as unknown as ApiRequest
    const job=scope.run(()=>useTrainingJob(api,enabled,done,failed))!;job.attach(jobId);await flushPromises();expect(localStorage.getItem(TRAINING_JOB_KEY)).toBe(jobId)
    expect(api).toHaveBeenCalledTimes(1);enabled.value=false;await nextTick();await vi.advanceTimersByTimeAsync(10000);expect(api).toHaveBeenCalledTimes(1)
    status='completed';enabled.value=true;await flushPromises();expect(done).toHaveBeenCalledWith('b');expect(job.busy.value).toBe(false);expect(localStorage.getItem(TRAINING_JOB_KEY)).toBeNull();scope.stop();await vi.advanceTimersByTimeAsync(10000);expect(api).toHaveBeenCalledTimes(2)
  })
  it('reload restores UUID, ignores late replies and retries transient failures without resubmitting',async()=>{
    vi.useFakeTimers();localStorage.setItem(TRAINING_JOB_KEY,jobId);const enabled=ref(true), pending=deferred<any>(), done=vi.fn(), scope=effectScope()
    const api=vi.fn().mockReturnValueOnce(pending.promise).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new ApiError('gone',404)) as unknown as ApiRequest
    const job=scope.run(()=>useTrainingJob(api,enabled,done,vi.fn()))!;expect(job.busy.value).toBe(true);enabled.value=false;await nextTick();pending.resolve({status:'completed',progress:100,result_model_id:'a'});await flushPromises();expect(done).not.toHaveBeenCalled()
    enabled.value=true;await flushPromises();expect(job.error.value).toBe('offline');await vi.advanceTimersByTimeAsync(1400);expect(job.busy.value).toBe(false);expect(job.error.value).toBe('gone');scope.stop()
  })
})

function mountedPage(component:any,page:string,api:ApiRequest=fixtureApi()) {
  history.replaceState(null,'',`/#${page}`);let workspace!:Workspace
  const Harness=defineComponent({setup(){workspace=useWorkspace(api);provide(workspaceKey,workspace);return ()=>h(component)}})
  const wrapper=mount(Harness,{global:{plugins:[ElementPlus],stubs:{FeatureImportance:true,DatasetPreview:true,TrainingProvenance:true,ClassificationEvaluation:true}}})
  return {wrapper,get workspace(){return workspace}}
}
describe('real page components',()=>{
  it('deleting a model invalidates its in-flight detail before selection completes',async()=>{
    vi.spyOn(ElMessageBox,'confirm').mockResolvedValue('confirm')
    const pending=deferred<any>(), api=(async(url:string)=>url==='/api/trained-models/a'?pending.promise:[]) as ApiRequest
    const {workspace}=mountedPage(TrainedModelsPage,'trained',api)
    const loading=workspace.openTrainedModel('a');await workspace.deleteTrainedModels(['a'])
    pending.resolve(model('a'));await loading;expect(workspace.selectedTrainedModel.value).toBeNull()
  })
  it('rapid dataset selection renders only latest fields and preserves Chinese names',async()=>{
    const {wrapper,workspace}=mountedPage(DatasetPage,'datasets');await vi.waitFor(()=>expect(workspace.datasets.value).toHaveLength(2))
    const rows=wrapper.findAll('.el-table__body tr');expect(rows).toHaveLength(2)
    await rows[0].trigger('click');await rows[1].trigger('click');await vi.waitFor(()=>expect(workspace.selectedDataset.value?.id).toBe('b'))
    await new Promise(resolve=>setTimeout(resolve,700));expect(workspace.selectedDataset.value?.id).toBe('b');expect(workspace.training.value.featureColumns).toEqual([...featureNames,'目標']);expect(wrapper.text()).toContain('資料集乙')
    workspace.activePage.value='trained';await nextTick();expect(workspace.datasetDetailLoading.value).toBe(false)
  })
  it('rapid model selection keeps full regression details, test-upload controls and latest model',async()=>{
    const {wrapper,workspace}=mountedPage(TrainedModelsPage,'trained');await vi.waitFor(()=>expect(workspace.trainedModels.value).toHaveLength(2))
    const rows=wrapper.findAll('.trained-model-list .el-table__body tr');expect(rows).toHaveLength(2);await rows[0].trigger('click');await rows[1].trigger('click')
    await vi.waitFor(()=>expect(workspace.selectedTrainedModel.value?.id).toBe('b'));await new Promise(resolve=>setTimeout(resolve,700));expect(workspace.selectedTrainedModel.value?.id).toBe('b')
    expect(wrapper.find('.unified-model-detail').exists()).toBe(true);expect(wrapper.find('.model-evaluation-panel').exists()).toBe(true)
    for (const label of ['Pearson R','MAPE','NRMSE','最大誤差','目標平均']) expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).toContain('0.976');expect(workspace.selectedTrainedModel.value?.feature_columns).toEqual(featureNames)
  })
  it('leaving a page invalidates model requests even when transport ignores abort',async()=>{
    const pending=deferred<any>();const api=(async(url:string)=>url==='/api/trained-models/a'?pending.promise:[]) as ApiRequest
    const {workspace}=mountedPage(TrainedModelsPage,'trained',api);const loading=workspace.openTrainedModel('a');workspace.activePage.value='history';await nextTick();pending.resolve(model('a'));await loading;expect(workspace.selectedTrainedModel.value).toBeNull()
  })
})
