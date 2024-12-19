const Category = require("../models/Category")
const mongoose = require("mongoose")

function getRandomInt(max) {
    return Math.floor(Math.random() * max)
  }

exports.createCategory = async (req,res) => {
    try{
        //fetch data from req body
        const {name,description} = req.body;

        //validate data
        if(!name || !description){
            return res.status(200).json({
                success:false,
                message:"Please enter data in all fields"
            });
        }

        //create tag in db
        const categoryDetails = await Category.create({name,description});
        
        return res.status(200).json({
            success:true,
            message:"Category created successfully",
            categoryDetails
        });
    }
    catch(err){
        return res.status(400).json({
            success:false,
            message:err.message
        });
    }
}

exports.showAllCategory = async (req,res) =>{
    try{
        const categoryData = await Category.find();
        console.log(categoryData)
        return res.status(200).json({
            success:true,
            message:"All Category fetched",
            data:categoryData
        });
    }
    catch(err){
        return res.status(400).json({
            success:false,
            message:err.message
        });
    }
}

// exports.categoryPageDetails = async (req,res) => {
//     try{
//         //get category id
//         const {categoryId} = req.body;
        
//         //get all courses corrosponding to that id
//         const categoryCourses = await Category.findById(categoryId).populate("courses").exec();
//         //validate courses
//         if(!categoryCourses){
//             return res.status(404).json({
//                 success:false,
//                 message:"No courses found in this category"
//             });
//         }
//         //get courses from diff category
//         const diffrentCourses = await Category.find({_id : {$ne:categoryId}}).populate("courses").exec();
//         //get top category courses

//         return res.status(200).json({
//             success:true,
//             data : {
//                 diffrentCourses,
//                 categoryCourses
//             }
//         });
//     }
//     catch(err){
//         return res.status(200).json({
//             success:false,
//             message:err.message
//         });
//     }
// }

exports.categoryPageDetails = async (req, res) => {
    try {
      const { categoryId } = req.body
  
      // Get courses for the specified category
      const selectedCategory = await Category.findById(categoryId)
        .populate({
          path: "courses",
          match: { status: "Published" },
          populate: "ratingAndReviews",
        })
        .exec()
  
      console.log("SELECTED COURSE", selectedCategory)
      // Handle the case when the category is not found
      if (!selectedCategory) {
        console.log("Category not found.")
        return res
          .status(404)
          .json({ success: false, message: "Category not found" })
      }
      // Handle the case when there are no courses
      if (!selectedCategory.courses) {
        console.log("No courses found for the selected category.")
        return res.status(404).json({
          success: false,
          message: "No courses found for the selected category.",
        })
      }
  
      // Get courses for other categories
      const categoriesExceptSelected = await Category.find({
        _id: { $ne: categoryId },
      })
      let differentCategory = await Category.findOne(
        categoriesExceptSelected[getRandomInt(categoriesExceptSelected.length)]
          ._id
      )
        .populate({
          path: "courses",
          match: { status: "Published" },
        })
        .exec()
      console.log()
      // Get top-selling courses across all categories
      const allCategories = await Category.find()
        .populate({
          path: "courses",
          match: { status: "Published" },
        })
        .exec()
      const allCourses = allCategories.flatMap((category) => category.courses)
      const mostSellingCourses = allCourses
        .sort((a, b) => b.sold - a.sold)
        .slice(0, 10)
  
      res.status(200).json({
        success: true,
        data: {
          selectedCategory,
          differentCategory,
          mostSellingCourses,
        },
      })
    } catch (error) {
      return res.status(500).json({
        success: false,
        message: "Internal server error",
        error: error.message,
      })
    }
}
  