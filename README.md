
# 1. Build Metrics *

## Complexity

A weighted formula:

```
Complexity = w₁ * (1 / CC)
           + w₂ * (1 / HC)
           + w₃ * SCS 
           + w₄ * CR    
           + w₅ * (1 / log(LOC + 2)) 
           + w₆ * (1 - UDR) 
           + w₇ * (1 - DCR)
```

**Where:**
- `CC` = Cyclomatic Complexity  
- `AC` = Halsted Complexity
- `SCS` = % of lines following style.   (1- V/LOC)  
- `CR` = Comment Ratio   (Comment Lines / Total Lines))  
- `LOC` = Lines of Code  
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Ratio  

---

### SCS (Source Code Simplicity)

```
SCS = (1 - V / LOC) * 100
```

- `V` = (Possibly number of violations or unused elements)  
- `LOC` = Lines of Code

---

## Maintainability

```
Maintainability = f(Complexity, Coupling, Cohesion, Dependency Quality)
```
