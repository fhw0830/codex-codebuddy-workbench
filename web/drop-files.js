(function(root){
  'use strict';
  function controller(onFiles,onHighlight){
    let depth=0;
    const isFiles=e=>[...(e.dataTransfer?.types||[])].includes('Files');
    return {
      dragenter(e){if(!isFiles(e))return;e.preventDefault();depth++;onHighlight(true);},
      dragover(e){if(!isFiles(e))return;e.preventDefault();e.dataTransfer.dropEffect='copy';},
      dragleave(){if(--depth<=0){depth=0;onHighlight(false);}},
      drop(e){if(!e.dataTransfer?.files?.length)return;e.preventDefault();depth=0;onHighlight(false);onFiles([...e.dataTransfer.files]);},
      dragend(){depth=0;onHighlight(false);}
    };
  }
  const api={controller};
  if(typeof module==='object'&&module.exports)module.exports=api;else root.CollabDrop=api;
})(typeof window==='object'?window:this);
