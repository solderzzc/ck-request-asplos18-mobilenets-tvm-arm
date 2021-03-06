#! /usr/bin/python
import ck.kernel as ck
import copy
import re
import argparse,json
import os

# ReQuEST description.
request_dict={
  'report_uid':'8b220a7f172a47d4', # unique UID for a given ReQuEST submission generated manually by user (ck uid)
                                   # the same UID will be for the report (in the same repo)

  'repo_uoa':'ck-request-asplos18-mobilenets-tvm-arm',
  'repo_uid':'c47366a47958ef4b',

  'repo_cmd':'ck pull repo:ck-request-asplos18-mobilenets-tvm-arm',

  'farm':'', # if farm of machines

  'algorithm_species':'4b8bbc192ec57f63' # image classification
}

# Platform tag.
platform_tags='firefly-rk3399'

# Batch size.
bs={
  'start':1,
  'stop':1,
  'step':1,
  'default':1
}

program='request-tvm-nnvm-inference'
dataset='image-jpeg-dnn-snake-224'

def do(i, arg):
    # Process arguments.
    if (arg.accuracy):
        experiment_type = 'accuracy'
        num_repetitions = 1
        cmd_key='test'
    else:
        experiment_type = 'performance'
        num_repetitions = arg.repetitions
        cmd_key='classify'

    random_name = arg.random_name
    share_platform = arg.share_platform

    # Detect basic platform info.
    ii={'action':'detect',
        'module_uoa':'platform',
        'out':'con'}
    if share_platform: ii['exchange']='yes'
    r=ck.access(ii)
    if r['return']>0: return r

    # Keep to prepare ReQuEST meta.
    platform_dict=copy.deepcopy(r)

    # Host and target OS params.
    hos=r['host_os_uoa']
    hosd=r['host_os_dict']

    tos=r['os_uoa']
    tosd=r['os_dict']
    tdid=r['device_id']

    ii={'action':'show',
        'module_uoa':'env',
        'tags':'dataset,imagenet,raw,val'}

    rx=ck.access(ii)
    if len(rx['lst']) == 0: return rx
    # FIXME: It's probably better to use CK_ENV_DATASET_IMAGE_DIR.
    img_dir_val = rx['lst'][0]['meta']['env']['CK_CAFFE_IMAGENET_VAL']

    if arg.accuracy:
        batch_count = len([f for f in os.listdir(img_dir_val)
           if f.endswith('.JPEG') and os.path.isfile(os.path.join(img_dir_val, f))])
    else:
        batch_count = 1

    ii={'action':'show',
        'module_uoa':'env',
        'tags':'dataset,imagenet,aux'}
    rx=ck.access(ii)
    if len(rx['lst']) == 0: return rx

    img_dir_aux = rx['lst'][0]['meta']['env']['CK_ENV_DATASET_IMAGENET_AUX']
    ii={'action':'load',
        'module_uoa':'program',
        'data_uoa':program}
    rx=ck.access(ii)
    if rx['return']>0: return rx
    mm=rx['dict']

    # Get compile-time and run-time deps.
    cdeps=mm.get('compile_deps',{})
    rdeps=mm.get('run_deps',{})
    rdeps.update(mm.get('run_cmds',{}).get(cmd_key,{}).get('run_deps',{}))

    # Merge rdeps with cdeps for setting up the pipeline (which uses
    # common deps), but tag them as "for_run_time".
    for k in rdeps:
        cdeps[k]=rdeps[k]
        cdeps[k]['for_run_time']='yes'

    depl=copy.deepcopy(cdeps['lib-nnvm-tvm'])
    if (arg.tos is not None) and (arg.did is not None):
        tos=arg.tos
        tdid=arg.did

    ii={'action':'resolve',
        'module_uoa':'env',
        'host_os':hos,
        'target_os':tos,
        'device_id':tdid,
        'out':'con',
        'deps':{'lib-nnvm-tvm':copy.deepcopy(depl)},
        'quiet':'yes'
    }
    r=ck.access(ii)
    if r['return']>0: return r

    udepl=r['deps']['lib-nnvm-tvm'].get('choices',[])
    if len(udepl)==0:
        return {'return':1, 'error':'no installed TVM'}
    cdeps['lib-nnvm-tvm']['uoa']=udepl[0]

    depm=copy.deepcopy(cdeps['mxnet-model'])

    ii={'action':'resolve',
        'module_uoa':'env',
        'host_os':hos,
        'target_os':tos,
        'device_id':tdid,
        'out':'con',
        'deps':{'mxnet-model':copy.deepcopy(depm)},
        'quiet':'yes'
    }
    r=ck.access(ii)
    if r['return']>0: return r

    udepm=r['deps']['mxnet-model'].get('choices',[])
    if len(udepm)==0:
        return {'return':1, 'error':'no installed mxnet-model'}

    cdeps['mxnet-model']['uoa']=udepm[0]

    ii={'action':'pipeline',
        'prepare':'yes',
        'dependencies':cdeps,

        'module_uoa':'program',
        'data_uoa':program,

        'target_os':tos,
        'device_id':tdid,

        'cmd_key':cmd_key,
        'dataset_uoa':dataset,

        'no_state_check':'yes',
        'no_compiler_description':'yes',
        'skip_calibration':'yes',

        'cpu_freq':'max',
        'gpu_freq':'max',

        'env':{
          'STAT_REPEAT':5
        },

        'flags':'-O3',
        'speed':'no',
        'energy':'no',

        'skip_print_timers':'yes',
        'out':'con'
    }

    r=ck.access(ii)
    if r['return']>0: return r
    fail=r.get('fail','')
    if fail=='yes':
        return {'return':10, 'error':'pipeline failed ('+r.get('fail_reason','')+')'}

    ready=r.get('ready','')
    if ready!='yes':
        return {'return':11, 'error':'pipeline not ready'}

    state=r['state']
    tmp_dir=state['tmp_dir']

    # Remember resolved deps for this benchmarking session.
    xcdeps=r.get('dependencies',{})
    # Clean pipeline.
    if 'ready' in r: del(r['ready'])
    if 'fail' in r: del(r['fail'])
    if 'return' in r: del(r['return'])

    pipeline=copy.deepcopy(r)

    for precision in ['float32','float16']:
        ck.out('')
        ck.out('Precision: '+precision)
        ck.out('')

        xprecision='fp32'
        if precision=='float16': xprecision='fp16'

        for lib_uoa in udepl:
           # Load lib.
           ii={'action':'load',
               'module_uoa':'env',
               'data_uoa':lib_uoa}
           r=ck.access(ii)
           if r['return']>0: return r

           lib_name=r['data_name']
           lib_tags=r['dict']['customize']['version']

           # Skip some libs with "in [..]" or "not in [..]".
           if arg.accuracy and lib_tags not in use_lib_tags: continue
           skip_compile='no'

           # For each  model*************************************************
           for model_uoa in udepm:
               # Load model.
               ii={'action':'load',
                   'module_uoa':'env',
                   'data_uoa':model_uoa}
               r=ck.access(ii)
               if r['return']>0: return r

               model_real_tags=r['dict']['tags']

               # Get the tags from e.g. 'Caffe model (net and weights) (inception-v3, fp32)'
               model_name=r['data_name']
               model_tags = re.match('MXNet model \(net and weights\) \((?P<tags>.*)\)', model_name)
               model_tags = model_tags.group('tags').replace(' ', '').replace(',', '-')

               record_repo='local'
               record_uoa='ck-request-asplos18-nnvm-tvm-arm-'+experiment_type+'.'+model_tags+'.'+xprecision

               # Prepare pipeline.
               ck.out('---------------------------------------------------------------------------------------')
               ck.out('%s - %s' % (lib_name, lib_uoa))
               ck.out('%s - %s' % (model_name, model_uoa))
               ck.out('Experiment - %s:%s' % (record_repo, record_uoa))

               # Prepare autotuning input.
               cpipeline=copy.deepcopy(pipeline)

               cpipeline['choices']['env']['CK_TVM_DTYPE']=precision

               # Reset deps and change UOA.
               new_deps={'lib-nnvm-tvm':copy.deepcopy(depl),
                         'mxnet-model':copy.deepcopy(depm)}

               new_deps['lib-nnvm-tvm']['uoa']=lib_uoa
               new_deps['mxnet-model']['uoa']=model_uoa

               jj={'action':'resolve',
                   'module_uoa':'env',
                   'host_os':hos,
                   'target_os':tos,
                   'device_id':tdid,
                   'deps':new_deps}
               r=ck.access(jj)
               if r['return']>0: return r

               cpipeline['dependencies'].update(new_deps)

               cpipeline['no_clean']=skip_compile
               cpipeline['no_compile']=skip_compile

               # Prepare common meta for ReQuEST tournament
               features=copy.deepcopy(cpipeline['features'])
               platform_dict['features'].update(features)

               r=ck.access({'action':'prepare_common_meta',
                            'module_uoa':'request.asplos18',
                            'platform_dict':platform_dict,
                            'deps':cpipeline['dependencies'],
                            'request_dict':request_dict})
               if r['return']>0: return r

               record_dict=r['record_dict']

               meta=r['meta']

               meta['model_precision']=xprecision

               if random_name:
                  rx=ck.gen_uid({})
                  if rx['return']>0: return rx
                  record_uoa=rx['data_uid']

               tags=r['tags']

               tags.append(experiment_type)

               tags.append('explore-mxnet-'+experiment_type)
               tags.append(lib_tags)
               tags.append(platform_tags)

               ii={'action':'autotune',
                  'module_uoa':'pipeline',
                  'data_uoa':'program',
                  'choices_order':[
                      [
                          '##choices#env#CK_BATCH_SIZE'
                      ]
                  ],
                  'choices_selection':[
                      {'type':'loop', 'start':bs['start'], 'stop':bs['stop'], 'step':bs['step'], 'default':bs['default']}
                  ],

                  'features_keys_to_process':['##choices#*'],

                  'iterations':-1,
                  'repetitions': num_repetitions,

                  'record':'yes',
                  'record_failed':'yes',

                  'record_params':{
                      'search_point_by_features':'yes'
                  },

                  'tags':tags,
                  'meta':meta,

                  'record_dict':record_dict,

                  'record_repo':record_repo,
                  'record_uoa':record_uoa,

                  'pipeline':cpipeline,
                  'out':'con'
               }
               r=ck.access(ii)
               if r['return']>0: return r

               fail=r.get('fail','')
               if fail=='yes':
                   return {'return':10, 'error':'pipeline failed ('+r.get('fail_reason','')+')'}

### end pipeline
    return {'return':0}

##############################################################################################
parser = argparse.ArgumentParser(description='Pipeline')
parser.add_argument("--target_os", action="store", dest="tos")
parser.add_argument("--device_id", action="store", dest="did")
parser.add_argument("--accuracy", action="store_true", default=False, dest="accuracy")
parser.add_argument("--repetitions", action="store", default=5, dest="repetitions")
parser.add_argument("--random_name", action="store_true", default=False, dest="random_name")
parser.add_argument("--share_platform", action="store_true", default=False, dest="share_platform")

myarg=parser.parse_args()

r=do({}, myarg)
if r['return']>0: ck.err(r)
