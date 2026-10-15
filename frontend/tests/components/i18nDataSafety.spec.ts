import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h, provide, nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import TrainedModelsPage from '../../src/pages/TrainedModelsPage.vue'
import ModelIdCell from '../../src/ModelIdCell.vue'
import { locale, t, type TranslationKey } from '../../src/i18n'
import { trainedModelMessages } from '../../src/trainedModelMessages'
import { useWorkspace } from '../../src/composables/useWorkspace'
import { workspaceKey, type Workspace } from '../../src/workspaceContext'
import { fixtureApi, featureNames, model } from '../fixtures/workspaceApi'
import type { ApiRequest } from '../../src/modelEvaluation'

afterEach(()=>{locale.value='zh-TW'})
function renderDetails(request:ApiRequest=fixtureApi()) {
  history.replaceState(null,'','/#trained');locale.value='zh-TW';let workspace!:Workspace
  const Harness=defineComponent({setup(){workspace=useWorkspace(request);provide(workspaceKey,workspace);return()=>h(TrainedModelsPage)}})
  const wrapper=mount(Harness,{global:{plugins:[ElementPlus],stubs:{FeatureImportance:true,TrainingProvenance:true,ClassificationEvaluation:true}}})
  workspace.selectedTrainedModel.value={...model('a'),status:'draft',target_column:'操作'}
  workspace.trainedModelRename.value='模型名稱'
  return {wrapper,workspace}
}
describe('explicit translation is separate from user data',()=>{
  it('classification details use a neutral target label instead of the numeric-only training label',async()=>{
    const {wrapper,workspace}=renderDetails();workspace.selectedTrainedModel.value!.problem_type='classification'
    for(const language of ['en','zh-TW'] as const){locale.value=language;await nextTick();expect(wrapper.text()).toContain(t('detailTargetColumn'));expect(wrapper.text()).not.toContain(language==='en'?'numeric only':'僅可選數值')}
  })
  it('repeated language switching translates labels without changing matching model/feature/target names',async()=>{
    const {wrapper,workspace}=renderDetails();await nextTick();const before=JSON.stringify(workspace.selectedTrainedModel.value)
    for(const language of ['en','zh-TW','en','zh-TW','en'] as const){
      locale.value=language;await nextTick()
      expect(wrapper.findAll('.feature-list .el-tag').map(tag=>tag.text())).toEqual(featureNames)
      expect(wrapper.findAll('.feature-list span[title]').map(tag=>tag.attributes('title'))).toEqual(featureNames)
      expect(wrapper.find('.unified-model-detail .result-heading').text()).toContain('模型名稱：'+t('modelDetails'))
      expect(wrapper.find('.unified-model-detail').text()).toContain('操作')
      expect(wrapper.text()).toContain(t('detailValidationPearson'));expect(wrapper.text()).toContain(t('detailTestPearson'))
      expect(wrapper.text()).toContain(t('detailValidationR2'));expect(wrapper.text()).toContain(t('detailTestR2'))
      expect(wrapper.text()).toContain(t('detailFoldR2Mean'))
      expect(wrapper.findAll('.unified-model-detail .el-tooltip__trigger')).toHaveLength(3)
      expect(wrapper.find('.model-evaluation-panel').exists()).toBe(true)
      expect(wrapper.find('.model-rename-card input').element.value).toBe('模型名稱')
      expect(JSON.stringify(workspace.selectedTrainedModel.value)).toBe(before)
    }
  })
  it('legacy notes and complete metric labels use locale keys, with no accumulated partial substitutions',async()=>{
    const {wrapper,workspace}=renderDetails();workspace.selectedTrainedModel.value!.evaluation_version='legacy';await nextTick()
    for(const language of ['en','zh-TW','en'] as const){locale.value=language;await nextTick();expect(wrapper.text()).toContain(t('detailLegacyWarning'));expect(wrapper.text()).toContain(t('detailMetricHelp'));expect(wrapper.text()).toContain(t('detailLegacyHelp'))}
  })
  it('translations interpolate once, leave unknown slots intact and render user values as text',async()=>{
    locale.value='en';expect(t('detailOofStrategy',{strategy:'Model Name {count} <b>發布</b>'})).toBe('OOF evaluation · Strategy: Model Name {count} <b>發布</b>')
    expect(t('detailFeatureCount',{})).toBe('Training features ({count})')
    for(const language of ['zh-TW','en'] as const){locale.value=language;for(const key of Object.keys(trainedModelMessages.en))expect(t(key as TranslationKey)).toBeTypeOf('string')}
    const {wrapper,workspace}=renderDetails();workspace.selectedTrainedModel.value!.name='<img src=x>模型名稱';await nextTick();expect(wrapper.find('.result-heading').text()).toContain('<img src=x>模型名稱');expect(wrapper.find('.result-heading img').exists()).toBe(false)
  })
  it('canonical ID is copied verbatim under both locales, with translated icon tooltip/accessible name',async()=>{
    const writeText=vi.fn().mockResolvedValue(undefined), id='00000000-0000-4000-8000-000000000016'
    const original=Object.getOwnPropertyDescriptor(navigator,'clipboard')
    Object.defineProperty(navigator,'clipboard',{value:{writeText},configurable:true})
    try {
      const wrapper=mount(ModelIdCell,{props:{modelId:id},global:{plugins:[ElementPlus]}})
      for(const language of ['zh-TW','en','zh-TW'] as const){locale.value=language;await nextTick();expect(wrapper.find('code').text()).toBe(id);expect(wrapper.find('button').attributes('aria-label')).toBe(t('copyModelId'));await wrapper.find('button').trigger('click');await flushPromises();expect(writeText).toHaveBeenLastCalledWith(id)}
      expect(writeText).toHaveBeenCalledTimes(3)
    } finally { if(original)Object.defineProperty(navigator,'clipboard',original);else Reflect.deleteProperty(navigator,'clipboard') }
  })
  it('language changes never rewrite the model name, target or feature columns sent to the training API',async()=>{
    const bodies:unknown[]=[], base=fixtureApi()
    const request:ApiRequest=async<T>(url:string,init?:RequestInit)=>{if(url==='/api/training/jobs'&&init?.method==='POST')bodies.push(JSON.parse(String(init.body)));return base<T>(url,init)}
    const {workspace}=renderDetails(request);workspace.activePage.value='training';await nextTick();await workspace.openDataset('b');workspace.setTarget('目標');workspace.training.value.modelName='模型名稱'
    locale.value='en';await nextTick();locale.value='zh-TW';await nextTick();await workspace.train()
    expect(bodies).toHaveLength(1);expect(bodies[0]).toMatchObject({model_name:'模型名稱',target_column:'目標',feature_columns:featureNames})
  })
})
