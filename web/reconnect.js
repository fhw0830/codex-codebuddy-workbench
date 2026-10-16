(function(root){
 'use strict';
 function create(options){
  const set=options.setTimeout||setTimeout,clear=options.clearTimeout||clearTimeout;
  let stopped=false,pending=false,connected=false,timer=null,opening=null,stream=null,abort=null,attempts=0,version=0;
  function closeStream(){if(opening!==null)clear(opening);opening=null;if(stream){stream.close();stream=null;}}
  function retry(){
   if(stopped||timer!==null)return;
   connected=false;closeStream();const delay=Math.min(10000,1000*Math.pow(2,Math.min(attempts++,4)));
   options.onState('reconnecting',delay);
   timer=set(()=>{timer=null;void connect();},delay);
  }
  async function connect(){
   if(stopped||pending)return;
   pending=true;const current=++version;abort=new AbortController();
   const timeout=set(()=>abort?.abort(),10000);
   if(!connected)options.onState(attempts?'reconnecting':'connecting',0);
   try{
    await options.synchronize(abort.signal);
    if(stopped||current!==version)return;
    closeStream();const source=options.createStream();stream=source;
    opening=set(()=>{if(stream===source)retry();},10000);
    source.onopen=()=>{
     if(stopped||stream!==source)return;
     if(opening!==null)clear(opening);opening=null;attempts=0;connected=true;options.onState('connected',0);
    };
    source.onerror=()=>{if(!stopped&&stream===source)retry();};
   }catch(error){if(!stopped&&current===version)retry();}
   finally{clear(timeout);pending=false;abort=null;}
  }
  return {
   start(){if(timer!==null)clear(timer);timer=null;return connect();},
   wake(){if(pending||stopped)return;if(timer!==null)clear(timer);timer=null;return connect();},
   stop(){stopped=true;version++;if(timer!==null)clear(timer);timer=null;abort?.abort();closeStream();}
  };
 }
 const api={create};if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabReconnect=api;
})(typeof window==='object'?window:this);
