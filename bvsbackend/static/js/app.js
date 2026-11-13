
		const sidebar=document.getElementById('sidebar');
		const overlay=document.getElementById('overlay');
		const menuToggle=document.getElementById('menuToggle');
		function setMenuOpen(open){sidebar.classList.toggle('open',open);overlay.classList.toggle('visible',open);menuToggle.setAttribute('aria-expanded',String(open));}
		menuToggle.addEventListener('click',()=>setMenuOpen(!sidebar.classList.contains('open')));
		overlay.addEventListener('click',()=>setMenuOpen(false));
		sidebar.querySelectorAll('a').forEach(link=>link.addEventListener('click',()=>setMenuOpen(false)));
		document.addEventListener('keydown',event=>{if(event.key==='Escape')setMenuOpen(false);});
	