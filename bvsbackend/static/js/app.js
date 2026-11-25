
		const sidebar=document.getElementById('sidebar');
		const overlay=document.getElementById('overlay');
		const menuToggle=document.getElementById('menuToggle');
		function setMenuOpen(open){sidebar.classList.toggle('open',open);overlay.classList.toggle('visible',open);menuToggle.setAttribute('aria-expanded',String(open));}
		menuToggle.addEventListener('click',()=>setMenuOpen(!sidebar.classList.contains('open')));
		overlay.addEventListener('click',()=>setMenuOpen(false));
		sidebar.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>setMenuOpen(false)));
		document.addEventListener('keydown',event=>{if(event.key==='Escape')setMenuOpen(false);});
		document.querySelectorAll('[data-async-assignment]').forEach(form=>form.addEventListener('submit',async event=>{
			event.preventDefault();
			const button=form.querySelector('[type="submit"]');
			const status=form.querySelector('.assignment-save-status');
			button.disabled=true;
			status.textContent='Saving assignments...';
			try{
				const response=await fetch(form.action,{method:'POST',body:new FormData(form),credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});
				const result=await response.json();
				if(!response.ok||!result.ok){status.textContent=Object.values(result.errors||{}).flat().map(error=>error.message).join(' ')||'Assignments were not saved. Please try again.';return;}
				status.textContent=result.message;
			}catch{
				status.textContent='Could not reach the server. Your assignments were not changed.';
			}finally{
				button.disabled=false;
			}
		}));
	